plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val releaseKeystore = System.getenv("FENBI_ANDROID_KEYSTORE")
val releaseKeystorePassword = System.getenv("FENBI_ANDROID_KEYSTORE_PASSWORD")
val releaseKeyAlias = System.getenv("FENBI_ANDROID_KEY_ALIAS")
val releaseKeyPassword = System.getenv("FENBI_ANDROID_KEY_PASSWORD")
val hasPrivateReleaseSigning = listOf(
    releaseKeystore,
    releaseKeystorePassword,
    releaseKeyAlias,
    releaseKeyPassword,
).all { !it.isNullOrBlank() }

android {
    namespace = "com.local.fenbistudy.capture"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.local.fenbistudy.capture"
        minSdk = 26
        targetSdk = 35
        versionCode = 10304
        versionName = "1.3.4"
    }

    buildFeatures { compose = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    signingConfigs {
        if (hasPrivateReleaseSigning) {
            create("releasePrivate") {
                storeFile = file(releaseKeystore!!)
                storePassword = releaseKeystorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }
    buildTypes {
        release {
            // The shipped artifact is personal-sideload signed. Supplying all
            // four FENBI_ANDROID_* variables produces a private release build.
            signingConfig = if (hasPrivateReleaseSigning) {
                signingConfigs.getByName("releasePrivate")
            } else {
                signingConfigs.getByName("debug")
            }
            isMinifyEnabled = false
        }
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
}
