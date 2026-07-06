plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.example.water_level_pro"
    compileSdk = 37
    
    // Fallback if flutter object is not fully initialized in IDE context
    val ndkVersionStr = try { flutter.ndkVersion } catch (e: Exception) { "25.2.9519653" }
    ndkVersion = ndkVersionStr

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.example.water_level_pro"
        minSdk = flutter.minSdkVersion
        targetSdk = 37
        
        val vCode = try { flutter.versionCode } catch (e: Exception) { 1 }
        val vName = try { flutter.versionName } catch (e: Exception) { "1.0.0" }
        
        versionCode = vCode
        versionName = vName
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            isMinifyEnabled = false
            isShrinkResources = false
        }
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
