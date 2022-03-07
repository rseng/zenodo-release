#!/usr/bin/env python3

# This script does the following.
# 1. Takes in a space separated list of changed files
# 2. For each changed file, adds a header (title) based on the filename
# 3. Sets output for the prepared files to move into the site


import argparse
import os
import json
import sys
from datetime import datetime
import requests


def read_file(filename):
    with open(filename, "r") as fd:
        content = fd.read()
    return content


def read_json(filename):
    with open(filename, "r") as fd:
        content = json.loads(fd.read())
    return content


ZENODO_TOKEN = os.environ.get("ZENODO_TOKEN")
ZENODO_HOST = "zenodo.org"
if not ZENODO_TOKEN:
    sys.exit("A ZENODO_TOKEN is required to be exported in the environment!")


def upload_archive(archive, zenodo_json, version, doi=None):
    """
    Upload an archive to zenodo
    """
    archive = os.path.abspath(archive)
    if not os.path.exists(archive):
        sys.exit("Archive %s does not exist." % archive)

    headers = {"Accept": "application/json"}
    params = {"access_token": ZENODO_TOKEN}

    if doi:
        depositions = requests.get(
            "https://zenodo.org/api/deposit/depositions",
            params=params,
            headers=headers,
        )
        if depositions.status_code not in [200, 201]:
            sys.exit("Cannot query depositions: %s, %s" % (depositions.status_code, depositions.json()))

        target_deposit = None
        for deposit in depositions.json():
            print("looking at deposit %s" % (deposit['doi']))
            if deposit['conceptdoi'] == doi:
                target_deposit = deposit

        if not target_deposit:
            sys.exit("Cannot find deposit with doi: '%s'. Are you currently editing it?" % (doi))

        # found the existing deposit - so let's make a new version.
        url = "%s/actions/newversion" % target_deposit['links']['self']
        new_version = requests.post(
            url,
            params=params,
            headers=headers,
        )
        if new_version.status_code not in [200, 201]:
            sys.exit("Cannot create a new version for doi '%s'. %s" % (doi, new_version.json()))

        # new_version is actually the next draft. cannot edit the existing doi above
        new_version = requests.get(
            new_version.json()['links']['latest_draft'],
            params=params,
            headers=headers,
        )
        if new_version.status_code not in [200, 201]:
            sys.exit("Cannot create a new version for doi '%s'. %s" % (doi, new_version.json()))

        # this draft is based off of version N-1, so let's remove N-1's artifacts to make room
        # for version N.
        for file in new_version.json()['files']:
            delete = requests.delete(
                file['links']['self'],
                params=params,
                headers=headers,
            )
            if delete.status_code not in [200, 204]:
                print("could not delete file %s: %s" % (file['filename'], delete.json()))

        response = new_version
    else:
        # Create an empty upload
        response = requests.post(
            "https://zenodo.org/api/deposit/depositions",
            params=params,
            json={},
            headers=headers,
        )
        if response.status_code not in [200, 201]:
            sys.exit(
                "Trouble requesting new upload: %s, %s"
                % (response.status_code, response.json())
            )

    upload = response.json()

    # Using requests files indicates multipart/form-data
    # Here we are uploading the new release file
    url = "https://zenodo.org/api/deposit/depositions/%s/files" % upload["id"]
    bucket_url = upload["links"]["bucket"]

    with open(archive, "rb") as fp:
        response = requests.put(
            "%s/%s" % (bucket_url, os.path.basename(archive)),
            data=fp,
            params=params,
        )
        if response.status_code != 200:
            sys.exit("Trouble uploading artifact %s to bucket" % archive)

    # Finally, load .zenodo.json and add version
    metadata = read_json(zenodo_json)
    metadata["version"] = version
    metadata["publication_date"] = str(datetime.now())
    if "upload_type" not in metadata:
        metadata["upload_type"] = "software"
    url = "https://zenodo.org/api/deposit/depositions/%s" % upload["id"]
    headers["Content-Type"] = "application/json"
    response = requests.put(
        url, data=json.dumps({"metadata": metadata}), params=params, headers=headers
    )
    if response.status_code != 200:
        sys.exit(
            "Trouble uploading metadata %s, %s" % response.status_code, response.json()
        )

    data = response.json()
    publish_url = data["links"]["publish"]
    r = requests.post(publish_url, params=params)
    if r.status_code not in [200, 201, 202]:
        sys.exit(
            "Issue publishing record: %s, %s" % (response.status_code, response.json())
        )

    published = r.json()
    print("::group::Record")
    print(json.dumps(published, indent=4))
    print("::endgroup::")
    for k, v in published["links"].items():
        print("::set-output name=%s::%s" % (k, v))


def get_parser():
    parser = argparse.ArgumentParser(description="Zenodo Uploader")
    subparsers = parser.add_subparsers(
        help="actions",
        title="actions",
        description="Upload to Zenodo",
        dest="command",
    )
    upload = subparsers.add_parser("upload", help="upload an archive to zenodo")
    upload.add_argument("archive", help="archive to upload")
    upload.add_argument(
        "--zenodo-json",
        dest="zenodo_json",
        help="path to .zenodo.json (defaults to .zenodo.json)",
        default=".zenodo.json",
    )
    upload.add_argument("--version", help="version to upload")
    upload.add_argument("--doi", help="an existing DOI to add a new version to")
    return parser


def main():
    parser = get_parser()

    def help(return_code=0):
        parser.print_help()
        sys.exit(return_code)

    # If an error occurs while parsing the arguments, the interpreter will exit with value 2
    args, extra = parser.parse_known_args()
    if not args.command:
        help()

    if not args.zenodo_json or not os.path.exists(args.zenodo_json):
        sys.exit(
            "You must provide an existing .zenodo.json as the first positional argument."
        )
    if not args.archive:
        sys.exit("You must provide an archive as the second positional argument.")
    if not args.version:
        sys.exit("You must provide a software version to upload.")

    # Prepare drafts
    if args.command == "upload":
        upload_archive(args.archive, args.zenodo_json, args.version, doi=args.doi)


if __name__ == "__main__":
    main()
