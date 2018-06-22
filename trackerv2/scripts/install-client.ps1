#Requires -RunAsAdministrator

Function Get-RandomPassword() {
    Param(
        [int]$length=14,
        [string[]]$charset
    )

    For ($loop=1; $loop -le $length; $loop++){
        $TempPassword+=($charset | Get-Random)
    }

    return $TempPassword
}

$ScriptDir = Get-Location
$Hostname = $env:COMPUTERNAME
$NodeAccount = "wotnode"
$FirewallRule = "WoT Tracker Access"
$AccountDescription = "WoT Tracker Node Account"
$HomeDir = "$env:SystemDrive\Users\$NodeAccount"
$PathOutFile = "wotnodepath.txt"
$TempDir = "$env:SystemDrive\TEMP"
$TaskName = "TrackerNode-Run"
$TaskDescription = "WoT Tracker Node Daily Task"

if (Get-WmiObject Win32_UserAccount -Filter "LocalAccount='true' and Name='$NodeAccount'"){
    Write-Error "$NodeAccount already exists on the system. Please run uninstall-client.bat and retry"
    exit 1
}

$PassChar = $NULL;For ($c=33;$c -le 126; $c++) { $PassChar+=,[char][byte]$c }
$Password = Get-RandomPassword -charset $PassChar

## Create user
Write-Output "Creating user"
if ($PSVersionTable.PSVersion.Major -ge 5 -and $PSVersionTable.PSVersion.MajorRevision -ge 1){
    New-LocalUser $NodeAccount -Description $AccountDescription -Password $Password -PasswordNeverExpires -ErrorAction Stop
    $NewUser = [adsi]"WinNT://$Hostname/$NodeAccount,user"
    $NewUser.Put("HomeDirectory", $HomeDir)
    $NewUser.SetInfo()
} else {
    $ADSIComp = [adsi]"WinNT://$Hostname"
    $NewUser = $ADSIComp.Create('User',$NodeAccount)
    $NewUser.SetPassword($Password)
    $NewUser.Put("description", $AccountDescription)
    $NewUser.Put("HomeDirectory", $HomeDir)
    $NewUser.userflags = 0x100000 # Don't expire password
    $NewUser.SetInfo()
}

## Launch python setup script
$seclogon = Get-Service -Name seclogon
if ($seclogon.StartType -eq "Disabled"){ Set-Service -Name seclogon -Computer $Hostname -StartupType Manual -ErrorAction Stop; Write-Debug "Enabled Secondary Login" }
if ($seclogon.Status -ne "Running"){ $seclogon.Start(); Write-Debug "Started Secondary Login" }

$NodeCred = New-Object -TypeName System.Management.Automation.PSCredential -ArgumentList $NodeAccount,(ConvertTo-SecureString -AsPlainText $Password -Force)
Write-Output "Setting up Python and files"
$Process1 = Start-Process $PSHOME\powershell.exe -WorkingDirectory $PSHome -Credential $NodeCred -ArgumentList "-command $ScriptDir\setup-python.ps1" -Wait -NoNewWindow

## Add scheduler task for running node
$TaskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -windowStyle Hidden -command "python node.py"' -WorkingDirectory "$HomeDir"
$TaskTime = [String]((([System.TimeZoneInfo]::Local).BaseUtcOffset.Hours + 23) % 24) + ":45"
$TaskTrigger = New-ScheduledTaskTrigger -Daily -At $TaskTime
#Register-ScheduledTask -Action $TaskAction -Trigger $TaskTrigger -TaskName $TaskName -Description $TaskDescription -User $NodeAccount -Password $Password -AsJob -TaskPath $TaskPath
$NodeTask = Register-ScheduledTask -Action $TaskAction -Trigger $TaskTrigger -TaskName $TaskName -Description $TaskDescription -User $NodeAccount -Password $Password
#$TaskPrincipal = New-ScheduledTaskPrincipal -UserId "$Hostname\$NodeAccount" -LogonType S4U
#Register-ScheduledTask -Action $TaskAction -Trigger $TaskTrigger -TaskName $TaskName -Description $TaskDescription -AsJob -TaskPath $TaskPath -Principal $TaskPrincipal

## Add Firewall exception

## Output installation summary to .ini or .json file somewhere
# There's no need for this anymore

#$jsonResults = [pscustomobject]@{
#    username = $NodeAccount
#    python = $false
#    home = $HomeDir
#}

#Write-Debug "Saving summary to JSON file"
#$jsonResults | ConvertTo-Json -Depth 10 | Out-File "installresults.json"

Write-Output "Setup is complete!"