#!/usr/bin/env python3

# This script does the following.
# 1. Takes in a space separated list of changed files
# 2. For each changed file, adds a header (title) based on the filename
# 3. Sets output for the prepared files to move into the site


import argparse
import os
import json
import sys
from glob import glob
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
if not ZENODO_TOKEN:
    sys.exit("A ZENODO_TOKEN is required to be exported in the environment!")


class Zenodo:
    """
    Zenodo client to handle shared API calls.
    """

    def __init__(self, sandbox=False):
        self.headers = {"Accept": "application/json"}
        self.params = {"access_token": ZENODO_TOKEN}
        self.set_host(sandbox)

    def set_host(self, sandbox=False):
        """
        Given a preference for sandbox (or not) set the API host
        """
        self.host = "zenodo.org"
        if sandbox:
            self.host = "sandbox.zenodo.org"

    def get(self, url):
        """
        Wrapper to get to handle adding host and adding params or headers
        """
        if not url.startswith("http"):
            url = "https://%s%s" % (self.host, url)
        return requests.get(url, params=self.params, headers=self.headers)

    def post(self, url):
        """
        Wrapper to post to handle adding host and adding params or headers
        """
        if not url.startswith("http"):
            url = "https://%s%s" % (self.host, url)
        return requests.post(url, params=self.params, headers=self.headers)

    def get_depositions(self):
        """
        Get all current depositions.
        """
        response = self.get("/api/deposit/depositions")
        if response.status_code not in [200, 201]:
            sys.exit(
                "Cannot query depositions: %s, %s"
                % (response.status_code, response.json())
            )
        return response.json()

    def find_deposit(self, doi):
        """
        Given a doi, find the deposit, return None if no match
        """
        deposits = self.get_depositions()

        # Look for the matching DOI
        target_deposit = None
        for deposit in deposits:
            if "doi" not in deposit:
                continue
            print("looking at deposit %s" % deposit["doi"])
            if deposit["conceptdoi"] == doi:
                print("Found deposit %s! 🎉️" % doi)
                target_deposit = deposit
                break

        return target_deposit

    def new_doi(self):
        """
        Create a new (empty) upload for a DOI
        """
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
        return response.json()

    def update_doi(self, doi):
        """
        Given an existing DOI, update with a new archives (or pattern of files).
        """
        target_deposit = self.find_deposit(doi)
        if not target_deposit:
            sys.exit(
                "Cannot find deposit with doi: '%s'. Are you currently editing it?"
                % doi
            )

        # If we have an unpublished draft - continue working onit
        if not target_deposit["submitted"]:
            draft = target_deposit
        else:
            # found the existing deposit - so let's make a new version.
            response = self.post(
                "%s/actions/newversion" % target_deposit["links"]["self"]
            )
            if response.status_code not in [200, 201]:
                sys.exit(
                    "Cannot create a new version for doi '%s'. %s"
                    % (doi, response.json())
                )
            draft = response.json()

        # this is actually the next draft. cannot edit the existing doi above
        response = self.get(draft["links"]["latest_draft"])
        if response.status_code not in [200, 201]:
            sys.exit("Cannot create a draft for doi '%s'. %s" % (doi, response.json()))
        new_version = response.json()

        # this draft is based off of version N-1, so let's remove N-1's artifacts to make room
        # for version N.
        for file in new_version.get("files", []):
            response = requests.delete(
                file["links"]["self"], params=self.params, headers=self.headers
            )
            if response.status_code not in [200, 204]:
                print(
                    "could not delete file %s: %s" % (file["filename"], response.json())
                )
        return new_version

    def upload_archive(self, upload, archive):
        """
        Given an upload response and archive, upload the new file!
        """
        # Using requests files indicates multipart/form-data
        # Here we are uploading the new release file
        url = "https://zenodo.org/api/deposit/depositions/%s/files" % upload["id"]
        bucket_url = upload["links"]["bucket"]

        with open(archive, "rb") as fp:
            response = requests.put(
                "%s/%s" % (bucket_url, os.path.basename(archive)),
                data=fp,
                params=self.params,
            )
            if response.status_code != 200:
                sys.exit("Trouble uploading artifact %s to bucket" % archive)

    def publish(self, data):
        """
        Given a data response from a new metadata upload, publish it.
        """
        publish_url = data["links"]["publish"]
        r = requests.post(publish_url, params=self.params)
        if r.status_code not in [200, 201, 202]:
            sys.exit("Issue publishing record: %s, %s" % (r.status_code, r.json()))

        published = r.json()
        print("::group::Record")
        print(json.dumps(published, indent=4))
        print("::endgroup::")
        for k, v in published["links"].items():
            print("::set-output name=%s::%s" % (k, v))

    def upload_metadata(self, upload, zenodo_json, version):
        """
        Given an upload response and zenodo json, upload new data

        Note that if we don't have a zenodo.json we could use the old one.
        """
        metadata = upload["metadata"]

        # updates from zenodo.json
        if zenodo_json:
            metadata.update(read_json(zenodo_json))
        metadata["version"] = version
        metadata["publication_date"] = str(datetime.now())

        # New .zenodo.json may be missing this
        if "upload_type" not in metadata:
            metadata["upload_type"] = "software"
        self.headers.update({"Content-Type": "application/json"})

        # Make the deposit!
        url = "https://zenodo.org/api/deposit/depositions/%s" % upload["id"]
        response = requests.put(
            url,
            data=json.dumps({"metadata": metadata}),
            params=self.params,
            headers=self.headers,
        )
        if response.status_code != 200:
            sys.exit(
                "Trouble uploading metadata %s, %s" % response.status_code,
                response.json(),
            )
        return response.json()


def upload_archive(archive, version, zenodo_json=None, doi=None, sandbox=False):
    """
    Upload an archive to an existing Zenodo "versions DOI"
    """
    archive = os.path.abspath(archive)
    if not os.path.exists(archive):
        sys.exit("Archive %s does not exist." % archive)

    cli = Zenodo(sandbox=sandbox)

    if doi:
        upload = cli.update_doi(doi=doi)
    else:
        if not zenodo_json:
            sys.exit("You MUST provided a .zenodo.json template to create a new DOI.")
        upload = cli.new_doi()

    # Use a glob matching pattern to upload new files (also ensures exist)
    for path in glob(archive):
        cli.upload_archive(upload, path)

    # Finally, load .zenodo.json and add version
    data = cli.upload_metadata(upload, zenodo_json, version)

    # Finally, publish
    cli.publish(data)


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

    if args.zenodo_json and not os.path.exists(args.zenodo_json):
        sys.exit("%s does not exist." % args.zenodo_json)
    if not args.archive:
        sys.exit("You must provide an archive as the second positional argument.")
    if not args.version:
        sys.exit("You must provide a software version to upload.")

    if args.command == "upload":
        upload_archive(
            archive=args.archive,
            zenodo_json=args.zenodo_json,
            version=args.version,
            doi=args.doi,
        )

    # We should not get here :)
    else:
        sys.exit("Unrecognized command %s" % args.command)


if __name__ == "__main__":
    main()
