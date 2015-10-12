To import the analytics-bundle.zip analytics artifacts shipped with
this zenpack:

1. Login to analytics as Internal Authentication/superuser/superuser.
2. Verify the the repository path /root/Public/Microsoft Windows Zenpack does not exist.
If it does, move this folder elsewhere in the analytics repository or
remove it altogether before proceeding.
3. Navigate to Manage->Server Settings->Import and browse to the
analytics-bundle.zip file included in the Zenpack.
4. Uncheck ALL Import options. It is absolutely critical to make sure
"Update" is NOT checked.
5. Click "Import" button. The zip file import should report a success flare.
6. Navigate to /root/Public/Microsoft Windows Zenpack in the analytics repository and
verify the the folder was successfully created.
7. Log out and login as a regular Zenoss analytics user and verify
that you can use the Domains and Views under the Public/Microsoft Windows Zenpack folder
