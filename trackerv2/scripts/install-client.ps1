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
$TaskDescription = "WoT Tracker Client Daily Run"

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
# Updates are to be fetched prior to running the client
$TaskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -windowStyle Hidden -command "python update.py client.json; python client.py client.json"' -WorkingDirectory "$HomeDir"
$TaskTime = [String]((([System.TimeZoneInfo]::Local).BaseUtcOffset.Hours + 24) % 24) + ":00"
$TaskTrigger = New-ScheduledTaskTrigger -Daily -At $TaskTime
$Task = Register-ScheduledTask -Action $TaskAction -Trigger $TaskTrigger -TaskName $TaskName -Description $TaskDescription -User $NodeAccount -Password $Password

## Add Firewall exception


## Create initial json needed to connect to server
$jsonClient = [pscustomobject]@{
    server = "http://changeme/"
    application_id = "demo"
    throttle = 10
    debug = False
}

$jsonClient | ConvertTo-Json -Depth 10 | Out-File $HomeDir\client.json

Write-Output "Setup is complete!"