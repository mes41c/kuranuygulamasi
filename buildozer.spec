[app]
title = Kuran Uygulaması
package.name = kuranapp
package.domain = com.github.mes41c
source.dir = .
source.include_exts = py,png,db,kv,ttf
version = 0.1
requirements = python3,git+https://github.com/kivy/kivy.git,git+https://github.com/kivy/pyjnius.git
orientation = portrait
fullscreen = 0

[android]
android.api = 34
android.minapi = 21
android.ndk_api = 21
android.archs = arm64-v8a
android.build_tools = 34.0.0

[buildozer]
log_level = 2
warn_on_root = 1