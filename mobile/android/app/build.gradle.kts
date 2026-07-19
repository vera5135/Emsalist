import org.gradle.api.GradleException
import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    keystorePropertiesFile.inputStream().use { keystoreProperties.load(it) }
}

fun signingValue(name: String): String? =
    (project.findProperty(name) as String?)
        ?: keystoreProperties.getProperty(name)
        ?: System.getenv(name)

val releaseKeystorePath = signingValue("EMSALIST_ANDROID_KEYSTORE_FILE")
val releaseKeyAlias = signingValue("EMSALIST_ANDROID_KEY_ALIAS")
val releaseKeyPassword = signingValue("EMSALIST_ANDROID_KEY_PASSWORD")
val releaseStorePassword = signingValue("EMSALIST_ANDROID_STORE_PASSWORD")
val hasReleaseSigning =
    !releaseKeystorePath.isNullOrBlank() &&
        !releaseKeyAlias.isNullOrBlank() &&
        !releaseKeyPassword.isNullOrBlank() &&
        !releaseStorePassword.isNullOrBlank()
val isReleaseTaskRequested =
    gradle.startParameter.taskNames.any { it.contains("Release", ignoreCase = true) }

android {
    namespace = "com.emsalist.emsalist_mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.emsalist.app"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        create("release") {
            if (hasReleaseSigning) {
                storeFile = rootProject.file(releaseKeystorePath!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    flavorDimensions += "environment"
    productFlavors {
        create("development") {
            dimension = "environment"
            applicationIdSuffix = ".dev"
            resValue("string", "app_name", "Emsalist Dev")
        }
        create("staging") {
            dimension = "environment"
            applicationIdSuffix = ".staging"
            resValue("string", "app_name", "Emsalist Staging")
        }
        create("production") {
            dimension = "environment"
            resValue("string", "app_name", "Emsalist")
        }
    }

    buildTypes {
        release {
            if (!hasReleaseSigning && isReleaseTaskRequested) {
                throw GradleException(
                    "Release signing is required. Provide EMSALIST_ANDROID_KEYSTORE_FILE, " +
                        "EMSALIST_ANDROID_KEY_ALIAS, EMSALIST_ANDROID_KEY_PASSWORD, and " +
                        "EMSALIST_ANDROID_STORE_PASSWORD through environment variables, " +
                        "Gradle properties, or android/key.properties."
                )
            }
            signingConfig = signingConfigs.getByName("release")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
