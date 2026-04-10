 #!/usr/bin/bash

adb root
adb remount
adb shell settings put global auto_time 0
adb shell settings put global auto_time_zone 0
adb shell settings put system time_12_24 12
# adb shell setprop persist.sys.timezone Europe/Paris
adb shell setprop persist.sys.timezone Asia/Shanghai

adb shell "date `date +%m%d%H%M%Y.%S`"
adb shell am broadcast -a android.intent.action.TIME_SET

adb shell am broadcast -a android.intent.action.TIMEZONE_CHANGED --es "time-zone" "Asia/Shanghai"
# adb shell am broadcast -a android.intent.action.TIMEZONE_CHANGED --es "time-zone" "Europe/Paris"

# echo "Modify route table"
# adb shell ip rule add from all lookup main pref 9000
#

# Android keep rebooting if USING WiFi as 192.168.25.100 instead of ETH0
# Temporary Solution is eth0 down/up to restore eth0's IP address to 192.168.1.3
# echo "eth0 down"
# adb shell ifconfig eth0 down

# echo "eth0 UP"
# adb shell ifconfig eth0 up


