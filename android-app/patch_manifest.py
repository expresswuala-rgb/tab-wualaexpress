import os

path = "android/app/src/main/AndroidManifest.xml"
s = open(path).read()

perms = """    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" android:maxSdkVersion="28" />
    <uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />"""

if "WRITE_EXTERNAL_STORAGE" not in s:
    s = s.replace("<application", perms + "\n\n  <application", 1)
    open(path, "w").write(s)
    print("Manifest patched")
else:
    print("Already patched")