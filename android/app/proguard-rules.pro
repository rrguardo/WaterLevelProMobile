# Flutter Wrapper
-keep class io.flutter.app.** { *; }
-keep class io.flutter.plugin.**  { *; }
-keep class io.flutter.util.**  { *; }
-keep class io.flutter.view.**  { *; }
-keep class io.flutter.**  { *; }
-keep class io.flutter.plugins.**  { *; }

# App
-keep class com.example.water_level_pro.** { *; }

# Plugins
-keep class es.antonborri.home_widget.** { *; }
-keep class dev.fluttercommunity.workmanager.** { *; }

# JSON / Network (just in case they get stripped in service)
-keep class org.json.** { *; }
-keep class java.net.** { *; }

# MethodChannels and plugin components
-keep class * implements io.flutter.plugin.common.MethodChannel$MethodCallHandler { *; }

# Ignore missing optional Play Services / Deferred Components classes
-dontwarn com.google.android.play.core.**
-dontwarn io.flutter.embedding.engine.deferredcomponents.**
