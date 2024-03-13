# Zenodo Action

This is a quick helper action to allow you to automatically update a package on zenodo
on release, and without needing to enable admin webhooks. To get this working you will need to:

1. Create an account on Zenodo
2. Under your name -> Applications -> Developer Applications -> Personal Access Tokens -> +New Token and choose both scopes for deposit
3. Add the token to your repository secrets as `ZENODO_TOKEN`
4. Create a .zenodo.json file for the root of your repository (see [template](.zenodo.json))
5. Add the example action (modified for your release) to your GitHub repository.

[Here is an example](https://doi.org/10.5281/zenodo.6326822) of an "all releases" DOI created by this action, and the metadata associated:

```console
doi https://doi.org/10.5281/zenodo.6326823
conceptdoi https://doi.org/10.5281/zenodo.6326822
conceptbadge https://zenodo.org/badge/doi/10.5281/zenodo.6326822.svg
badge https://zenodo.org/badge/doi/10.5281/zenodo.6326823.svg
bucket https://zenodo.org/api/files/dbcddadd-4ea9-4f66-8045-e15552399dbc
latest https://zenodo.org/api/records/6326823
latest html https://zenodo.org/record/6326823
record https://zenodo.org/api/records/6326823
record html https://zenodo.org/record/6326823
```
 
You'll notice for this release there are several associated DOIs, and what this means is that the DOI [https://doi.org/10.5281/zenodo.6326822](https://doi.org/10.5281/zenodo.6326822)
will always link to the latest, which is typically what we want.

**Important** You CANNOT create a release online first and then try to upload to the same DOI.
If you do this, you'll get:

```python
{'status': 400,
 'message': 'Validation error.',
 'errors': [{'field': 'metadata.doi',
   'message': 'The prefix 10.5281 is administrated locally.'}]}
```

I think this is kind of silly, but that's just me. So the way to go is likely to:

1. Create a new DOI on the first go when you don't have one
2. Add the "all releases" DOI to your action to update that one for all releases after that!

## Usage

When looking at artifacts in Zenodo you'll see a versions card like the image below.  This artifact has
only one version, 0.0.15. By default, this is the behavior of this action - to create brand new artifacts
with only one version.

If, however, you'd like to make new versions you can specify the doi that represents *all*
versions. In this image you would specify `10.5281/zenodo.6326822`.  This action will then
create new versions tied to this DOI.

![Zenodo card for versions. '0.0.15' is the only version and a DOI of 10.5281/zenodo.6326823. The footer of the card has a site all versions with DOI 10.5281/zenodo.6326822](img/zenodo_versions.png)

### GitHub Action

After you complete the steps above to create the metadata file, you have two options.

#### Existing DOI

If you have an existing DOI that is of the **all versions** type meaning we can update it, you should provide it to the action.
The example below shows running a release workflow and providing an archive to update to a new version (**released under the same DOI**)

```yaml
name: Zenodo Release

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-20.04

    steps:
    - uses: actions/checkout@v3
    - name: download archive to runner
      env:
        tarball: ${{ github.event.release.tarball_url }}
        zipball: ${{ github.event.release.zipball_url }}
      # add the suffix to the name of the file so type is recognized when downloading from Zenodo
      # .tar.gz for tarball and .zip for zipball
      # Archiving the zipball will cause Zenodo to show a preview of the contents of the zipball while using tarball will not.
      run: |
        name=$(basename ${zipball}).zip  
        curl -L $zipball > $name
        echo "archive=${name}" >> $GITHUB_ENV

    - name: Run Zenodo Deploy
      uses: rseng/zenodo-release@main
      with:
        token: ${{ secrets.ZENODO_TOKEN }}
        version: ${{ github.event.release.tag_name }}
        zenodo_json: .zenodo.json   # optional
        html_url: ${{ github.event.release.html_url }} # optional to include link to the GitHub release
        archive: ${{ env.archive }}

        # Optional DOI for all versions. Leaving this blank (the default) will create
        # a new DOI on every release. Use a DOI that represents all versions will
        # create a new version for this existing DOI.
        #
        # Newer versions have their own DOIs, but they're also linked to this DOI
        # as a different version. When using this, use the DOI for all versions.
        doi: '10.5281/zenodo.6326822'
```

Notice how we are choosing to use the .tar.gz (you could use the zip too at `${{ github.event.release.zipball_url }}`).
Note that the "zenodo.json" is optional only if you've already created the record with some metadata. If you provide it,
it will be used to update metadata found with the previous upload. If you don't provide it, the previous upload will
only be updated for the date and version. Note that we are considering adding an ability to upload from new authors found
in the commit history, but this is not implemented yet.

#### New DOI

If you want to be creating fresh DOIs and releases (with no shared DOI for all versions) for each one, just remove the doi variable. Note
that for this case, the .zenodo.json is required as there isn't a previous record to get it from.

```yaml
name: Zenodo Release

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-20.04

    steps:
    - uses: actions/checkout@v3
    - name: download archive to runner
      env:
        tarball: ${{ github.event.release.tarball_url }}
      run: |
        name=$(basename ${tarball})        
        curl -L $tarball > $name
        echo "archive=${name}" >> $GITHUB_ENV

    - name: Run Zenodo Deploy
      uses: rseng/zenodo-release@main
      with:
        token: ${{ secrets.ZENODO_TOKEN }}
        version: ${{ github.event.release.tag_name }}
        zenodo_json: .zenodo.json  # required
        archive: ${{ env.archive }}
```

#### Archives

For both of the above, instead of an exact archive path you can also use a pattern to give to Python's `glob.glob`. E.g.,:

```yaml
      with:
        archive: "files/*.tar.gz"
```

Note that we will be testing support for more than one path or pattern soon.
We also grab the version as the release tag. We are also running on the publication of a release.

#### Outputs

If you want to see or do something with the outputs, add an `id` to the deploy step and do:

```yaml
    - name: Run Zenodo Deploy
      id: deploy
      uses: rseng/zenodo-release@main
      with:
        token: ${{ secrets.ZENODO_TOKEN }}
        version: ${{ github.event.release.tag_name }}
        zenodo_json: .zenodo.json
        archive: ${{ env.archive }}

    - name: View Outputs
      env:
        doi: ${{ steps.deploy.outputs.doi }} 
        conceptdoi: ${{ steps.deploy.outputs.conceptdoi }} 
        conceptbadge: ${{ steps.deploy.outputs.conceptbadge }} 
        badge: ${{ steps.deploy.outputs.badge }} 
        bucket: ${{ steps.deploy.outputs.bucket }} 
        latest: ${{ steps.deploy.outputs.latest }} 
        latest_html: ${{ steps.deploy.outputs.latest_html }} 
        record: ${{ steps.deploy.outputs.record }} 
        record_html: ${{ steps.deploy.outputs.record_html }} 
      run: |
        echo "doi ${doi}"
        echo "conceptdoi ${conceptdoi}"
        echo "conceptbadge ${conceptbadge}"
        echo "badge ${badge}"
        echo "bucket ${bucket}"
        echo "latest ${latest}"
        echo "latest html ${latest_html}"
        echo "record ${record}"
        echo "record html ${record_html}"
```

### Local

If you want to use the script locally (meaning to manually push a release) you can wget
or download the release (usually .tar.gz or .zip) and then export your zenodo token and do
the following:

```bash
export ZENODO_TOKEN=xxxxxxxxxxxxxxxxxxxx

                                  # archive    # multi-version DOI                 # new version
$ python scripts/deploy.py upload 0.0.0.tar.gz --doi 10.5281/zenodo.6326822        --version 0.0.0
```

