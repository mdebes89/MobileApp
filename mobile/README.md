# History Audiobooks — Mobile (Flutter)

Android client for the History Audiobooks backend. Enter a topic, pick filters
(length 10/30/60 min, male/female voice, language), and stream an AI-generated
history audiobook.

## Stack

- Flutter (Material 3), Riverpod state management, dio HTTP client
- Google Sign-In (ID token verified by the backend)
- just_audio streaming playback with position resume + playback speed
- RevenueCat (Google Play Billing) subscriptions with entitlement check
- Firebase Cloud Messaging: "audiobook ready" push navigates to the player

## Build & run

```bash
flutter pub get
flutter run \
  --dart-define=API_BASE_URL=http://10.0.2.2:8000 \
  --dart-define=GOOGLE_SERVER_CLIENT_ID=<your-web-server-client-id> \
  --dart-define=REVENUECAT_API_KEY=<your-revenuecat-key>
```

`API_BASE_URL` defaults to the Android emulator's host loopback
(`http://10.0.2.2:8000`).

## Configuration

| dart-define | Purpose |
| --- | --- |
| `API_BASE_URL` | Backend base URL |
| `GOOGLE_SERVER_CLIENT_ID` | OAuth Web client ID used for Google Sign-In ID tokens |
| `REVENUECAT_API_KEY` | RevenueCat public SDK key (Google Play Billing) |

Firebase (`google-services.json` in `mobile/android/app/`) is optional in dev —
push is disabled gracefully when it is missing.

## Screens

- **Login**: Google Sign-In only
- **Home**: topic search + shared catalog grid; "Generate" opens the filter sheet
  (length / voice / language), then polls status and shows "Generating your audiobook…"
- **Player**: chapter list, streaming playback, position resume, playback speed chips
- **Library**: the user's requested audiobooks with live status
- **Paywall**: RevenueCat offerings, purchase and restore

## Tests

```bash
flutter analyze
flutter test
```
