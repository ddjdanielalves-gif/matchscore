"""Configures release signing on the Capacitor-generated Android project.

Usage: python scripts/configure_android_signing.py <android_dir>
Requires <android_dir>/key.properties and a keystore file in the same dir.
Idempotent: safe to run on every build.
"""
from __future__ import annotations

import pathlib
import sys


def main() -> None:
    android_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("android")
    gradle = android_dir / "app" / "build.gradle"
    text = gradle.read_text(encoding="utf-8")

    if "keystorePropertiesFile" in text:
        print("signing already configured")
        return

    inject = (
        "android {\n"
        "    def keystorePropertiesFile = rootProject.file(\"key.properties\")\n"
        "    def keystoreProperties = new Properties()\n"
        "    if (keystorePropertiesFile.exists()) {\n"
        "        keystoreProperties.load(new FileInputStream(keystorePropertiesFile))\n"
        "    }\n"
    )
    if "android {\n" not in text:
        print("ERROR: android block not found", file=sys.stderr)
        sys.exit(1)
    text = text.replace("android {\n", inject, 1)

    old_buildtypes = (
        "    buildTypes {\n"
        "        release {\n"
        "            minifyEnabled false\n"
        "            proguardFiles getDefaultProguardFile('proguard-android.txt'), 'proguard-rules.pro'\n"
        "        }\n"
        "    }\n"
    )
    new_buildtypes = (
        "    signingConfigs {\n"
        "        release {\n"
        "            if (keystorePropertiesFile.exists()) {\n"
        "                storeFile rootProject.file(keystoreProperties['storeFile'])\n"
        "                storePassword keystoreProperties['storePassword']\n"
        "                keyAlias keystoreProperties['keyAlias']\n"
        "                keyPassword keystoreProperties['keyPassword']\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "    buildTypes {\n"
        "        release {\n"
        "            minifyEnabled false\n"
        "            proguardFiles getDefaultProguardFile('proguard-android.txt'), 'proguard-rules.pro'\n"
        "            signingConfig signingConfigs.release\n"
        "        }\n"
        "    }\n"
    )
    if old_buildtypes not in text:
        print("ERROR: buildTypes release block not found", file=sys.stderr)
        sys.exit(1)
    text = text.replace(old_buildtypes, new_buildtypes, 1)

    gradle.write_text(text, encoding="utf-8")
    print("release signing configured")


if __name__ == "__main__":
    main()
