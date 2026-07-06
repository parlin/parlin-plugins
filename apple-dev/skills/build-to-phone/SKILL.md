---
name: build-to-phone
description: Use when asked to build, install, or deploy the current iOS/watchOS app project onto a physical iPhone or iPad — "build to my phone", "put this on my device", "install on my iPhone". Not for Simulator runs and not for TestFlight/App Store distribution.
---

# Build to Phone

Build the iOS project in (or near) the current directory and install it on a physical
device over USB/Wi-Fi — entirely from the CLI, no Xcode GUI, no Simulator.

## Steps

1. **Find the project.** Nearest of: `project.yml` (XcodeGen — `cd` to the directory
   containing it and run `xcodegen generate`), `*.xcworkspace`, `*.xcodeproj`. Search
   the cwd, then one level down, then upward. A project-local run skill wins only if
   it covers *physical-device* installs (Simulator-only skills don't apply here).
2. **Pick the device.** `xcrun devicectl list devices` — keep rows whose State
   *contains* `available` (it reads e.g. `available (paired)`) and whose Model is an
   iPhone/iPad. Exactly one → use it. Several → AskUserQuestion (multiple choice).
   None → tell the user to plug in / unlock / join the same Wi-Fi and retry; do NOT
   silently fall back to the Simulator.
3. **Pick the scheme.** `xcodebuild -list -json`. Use the iOS *application* scheme —
   ignore watch-only, extension, test, and Swift-package schemes when the destination
   is an iPhone (an embedded watch app builds automatically with its host scheme;
   disambiguate by target names if scheme names don't make it obvious). Genuinely
   several candidates → fold into the same question as the device.
4. **Build** (Debug unless told otherwise) — output is huge, so tail it and check for
   `** BUILD SUCCEEDED **`:
   ```bash
   xcodebuild -project <X>.xcodeproj -scheme <S> -destination 'generic/platform=iOS' \
     -allowProvisioningUpdates -configuration Debug -derivedDataPath build/dd build
   ```
5. **Install** — `<ID>` is the **Identifier column from step 2** (a CoreDevice UUID;
   there is no "UDID" column, and this UUID is what devicectl wants):
   ```bash
   xcrun devicectl device install app --device <ID> \
     build/dd/Build/Products/Debug-iphoneos/<App>.app
   ```
6. **Verify + report:** `xcrun devicectl device info apps --device <ID>` — the app row's
   version/build must match the built `.app`'s Info.plist (`CFBundleShortVersionString`
   / `CFBundleVersion`). If the project has a watch target, tell the user the watch app
   does NOT install this way (see failure table). To launch:
   `xcrun devicectl device process launch --device <ID> <bundle-id>`.

## Failures you WILL hit

| Symptom | Fix |
|---|---|
| `The device is locked` (0xE80000E2) | Ask the user to unlock the phone, rerun the same install — nothing else is wrong |
| `CoreSimulator is out of date` noise in xcodebuild output | Harmless for device builds; ignore it (only blocks Simulator destinations) |
| Signing / provisioning error | Set `DEVELOPMENT_TEAM` to the team named in the laptop-wide CLAUDE.md (*Apple Code Signing* section); keep `-allowProvisioningUpdates` |
| Embedded watch app not on the watch after install | `devicectl` never pushes watch apps. iPhone Watch app → Available Apps → Install — and bump `CFBundleVersion` first or the sync treats it as a no-op |
| Device missing from `devicectl list devices` | Unlock it, check cable/same-Wi-Fi, retry; `unavailable` rows can't be used |

## Conventions

- Debug configuration, device build (`generic/platform=iOS`) — never a Simulator
  destination for this skill.
- `-derivedDataPath` inside the project's gitignored `build/` directory so the .app
  path is predictable for the install step.
- Never change signing settings or bundle ids without confirming with the user.
