#Requires -RunAsAdministrator
[CmdletBinding()]
Param(
	[Parameter(Mandatory=$True)][ValidateSet("server","client")][String]$uninstalling
)

$Hostname = $env:COMPUTERNAME
$NodeAccount = "wot$uninstalling"
$FirewallRule = "WoT Tracker Access"
$HomeDir = "$env:SystemDrive\Users\$NodeAccount"
$TextInfo = (Get-Culture).TextInfo
$TaskName = "Tracker$($TextInfo.ToTitleCase($uninstalling))-Run"

## Check Python
# Skipping. If installed locally, it will be within the user folder and removed later in the script anyways

## Delete scheduler task for running node
Write-Output "Removing scheduled task"
Unregister-ScheduledTask $TaskName -Confirm:$false
If ($uninstalling -eq "server") {
	Unregister-ScheduledTask "TrackerServer-Sync" -Confirm:$false
}

## Delete Firewall exception

## Delete home directory
Write-Output "Removing $HomeDir"
Write-Debug "Taking ownership of the home folder (may take a while)"
takeown /f $HomeDir /r /d y | Out-Null
Write-Debug "Opening permissions for Administrators"
icacls $HomeDir /grant administrators:F /t 2>&1 | Out-Null
Write-Debug "Removing directory"
Remove-Item $HomeDir -Recurse -Force

## Delete user
Write-Output "Removing user $NodeAccount"
if ($PSVersionTable.PSVersion.Major -ge 5 -and $PSVersionTable.PSVersion.MajorRevision -ge 1){
    Remove-LocalUser $NodeAccount
} else {
    $ADSIComp = [adsi]"WinNT://$Hostname"
    $ADSIComp.Delete('User',$NodeAccount)
}
