---
name: testflight
description: Use when asked to push, upload, ship, or release an iOS/watchOS build to TestFlight or App Store Connect — "push to TestFlight", "new beta build", "upload to ASC". Not for local device installs (use build-to-phone) and not for App Store review submission.
---

# TestFlight

Archive the current iOS project and upload it to App Store Connect entirely from the
CLI — no Xcode GUI, no Organizer. Machine/team facts (team ID, ASC API key ID + issuer
ID, existing Distribution cert) live in the laptop-wide CLAUDE.md under *Apple Code
Signing* / *App Store Connect API* — read that section first and use those values.

## Steps

1. **Project + version bump.** Locate the project as in apple-dev:build-to-phone
   step 1. Read the current `CFBundleVersion` from `project.yml` (XcodeGen) or the
   targets' Info.plists, bump it (+1, integer, use the NEW number as `<build>` below)
   in **every** target — an embedded watch app must carry the *same* version/build as
   its host or validation fails. XcodeGen projects: edit `project.yml`, then
   `xcodegen generate`. If another machine may have uploaded builds, check ASC for a
   higher existing build number first.
2. **Archive.** Pass `-configuration Release` explicitly (don't trust the scheme's
   archive config) and use absolute paths here too — cwd drift breaks relative ones.
   Archiving signs with the local *Development* cert and cached profiles, so no
   `-authenticationKey*` flags here; `-allowProvisioningUpdates` is safe at this step
   because nothing needs cloud signing yet. (If archive signing fails on a fresh
   machine, fix the Development cert/team per CLAUDE.md — adding API-key flags won't
   help.)
   ```bash
   xcodebuild -project <abs>/<X>.xcodeproj -scheme <S> -configuration Release \
     -destination 'generic/platform=iOS' -allowProvisioningUpdates \
     -archivePath <abs>/build/<App><build>.xcarchive archive
   ```
3. **exportOptions.plist** (keep next to the project; reuse if one exists):
   `method` app-store-connect · `teamID` from CLAUDE.md · `destination` upload ·
   `uploadSymbols` true · `manageAppVersionAndBuildNumber` false · `signingStyle`
   **manual** · `signingCertificate` "Apple Distribution" · `provisioningProfiles`
   mapping **every bundle id in the archive** (host app AND embedded watch app) to its
   App Store profile name. To find existing profile names: decode the installed ones
   (`security cms -D -i ~/Library/MobileDevice/Provisioning\ Profiles/<uuid>.mobileprovision`
   → `Name` key) or list via ASC API `GET /v1/profiles`.
4. **Export + upload.** Takes 10–20 min — run in the background and watch the output
   for `EXPORT SUCCEEDED` / `EXPORT FAILED` / `error:`. Use absolute paths.
   ```bash
   xcodebuild -exportArchive -archivePath <abs>/build/<App><build>.xcarchive \
     -exportOptionsPlist <abs>/exportOptions.plist \
     -authenticationKeyPath ~/.appstoreconnect/private_keys/AuthKey_<KEYID>.p8 \
     -authenticationKeyID <KEYID> -authenticationKeyIssuerID <ISSUER>
   ```
5. **Report.** "Upload succeeded" means App Store Connect is processing (5–30 min
   before the build shows in TestFlight). `ITSAppUsesNonExemptEncryption: false` in
   the Info.plist pre-answers the export-compliance question.

## Failure table

| Symptom | Fix |
|---|---|
| `Cloud signing permission error` | The API key cannot mint Xcode-managed certs/profiles. Stay on the manual-signing path above — retrying with automatic signing will always fail |
| `No signing certificate "iOS Distribution"` | Check `security find-identity -v -p codesigning`. If no Apple Distribution identity exists locally, and none on the team: creating one is an **account-wide change — get explicit user approval first**, then CSR → ASC API `POST /v1/certificates` (DISTRIBUTION) → import cert + private key into the login keychain |
| `Provisioning profile … doesn't include signing certificate` | Profile predates the cert. Create App Store profiles via ASC API `POST /v1/profiles` (`IOS_APP_STORE`, linked to the cert's resource id) for **each** bundle id incl. the watch app; write the `.mobileprovision` files to `~/Library/MobileDevice/Provisioning Profiles/` |
| Progress sits at "Uploading to App Store Connect…" | Normal for minutes at a time — keep waiting/monitoring |
| `Couldn't load -exportOptionsPlist … no such file` | Relative path resolved against a drifted cwd — use absolute paths |

## Conventions

- Never create certificates, revoke anything, or change API-key permissions without
  explicit user approval in that session.
- Issuer/key IDs stay in the laptop-wide CLAUDE.md — never hardcode them into
  committed project files or this skill.
- ASC API calls authenticate with a short-lived ES256 JWT built from the `.p8` key
  (`pyjwt` + `cryptography`).
