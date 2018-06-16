#Requires -RunAsAdministrator

$Hostname = $env:COMPUTERNAME
$NodeAccount = "wotnode"
$FirewallRule = "WoT Tracker Access"
$HomeDir = "$env:SystemDrive\Users\$NodeAccount"
$PathOutFile = "wotnodepath.txt"

## Check Python

## Delete scheduler task for running node

## Delete Firewall exception

## Delete home directory

takeown /f $HomeDir /r /d y | Out-Null
icacls $HomeDir /grant administrators:F /t 2>&1 | Out-Null
Remove-Item $HomeDir -Recurse -Force

## Delete user
if ($PSVersionTable.PSVersion.Major -ge 5 -and $PSVersionTable.PSVersion.MajorRevision -ge 1){
    Remove-LocalUser $NodeAccount
} else {
    $ADSIComp = [adsi]"WinNT://$Hostname"
    $ADSIComp.Delete('User',$NodeAccount)
}

## Output installation summary to .ini or .json file somewhere
