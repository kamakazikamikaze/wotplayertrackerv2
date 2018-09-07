#Requires -RunAsAdministrator
[CmdletBinding()]
Param(
	[Parameter(Mandatory=$True)][ValidateSet("server","client")][String]$installing
)

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

$TextInfo = (Get-Culture).TextInfo
$ScriptDir = Get-Location
$Hostname = $env:COMPUTERNAME
$NodeAccount = "wot$installing"
$FirewallRule = "WoT Tracker Access"
$AccountDescription = "WoT Tracker $($TextInfo.ToTitleCase($installing)) Account"
$HomeDir = "$env:SystemDrive\Users\$NodeAccount"
$TempDir = "$env:SystemDrive\TEMP"
$TaskName = "Tracker$($TextInfo.ToTitleCase($installing))-Run"
$TaskDescription = "WoT Tracker $($TextInfo.ToTitleCase($installing)) Daily Run"
If ($installing -eq "server") {
	$Minute = 0
	$TaskCmd = "python server.py ..\..\config\server.json -c ..\..\config\client.json -f ..\..\files"
	$TaskDir = "$Homedir\wotplayertrackerv2\trackerv2\server"
} Else {
	$Minute = 1
	$TaskCmd = 'python update.py client.json; python client.py client.json'
	$TaskDir = "$Homedir"
}

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
$Process1 = Start-Process $PSHOME\powershell.exe -WorkingDirectory $PSHome -Credential $NodeCred -ArgumentList "-command $ScriptDir\setup-executables.ps1 $installing" -Wait -NoNewWindow

## Add scheduler task for running node
# Updates are to be fetched prior to running the client
$TaskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -windowStyle Hidden -command "$TaskCmd"' -WorkingDirectory "$TaskDir"
$TaskTime = [String]((([System.TimeZoneInfo]::Local).BaseUtcOffset.Hours + 24) % 24) + ':' + [String]((([System.TimeZoneInfo]::Local).BaseUtcOffset.Minutes + 60 + $Minute) % 60)
$TaskTrigger = New-ScheduledTaskTrigger -Daily -At $TaskTime
$Task = Register-ScheduledTask -Action $TaskAction -Trigger $TaskTrigger -TaskName $TaskName -Description $TaskDescription -User $NodeAccount -Password $Password

## Add Firewall exception

If ($installing -eq "server") {
	$GitAction = New-ScheduledTaskAction -Execute 'git.exe' -Argument 'pull' -WorkingDirectory "$HomeDir\wotplayertrackerv2"
	$GitTime = [String]((([System.TimeZoneInfo]::Local).BaseUtcOffset.Hours + 23) % 24)
	$GitTrigger = New-ScheduledTaskTrigger -Daily -At $GitTime
	$Git = Register-ScheduledTask -Action $GitAction -Trigger $GitTrigger -TaskName "TrackerServer-Sync" -Description "WoT Tracker Sync Server Code" -User $NodeAccount -Password $Password
		
}
	
Write-Output "Setup is complete!"
