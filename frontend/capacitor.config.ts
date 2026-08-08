import type { CapacitorConfig } from "@capacitor/cli"

const config: CapacitorConfig = {
  appId: "com.matchscore.app",
  appName: "MatchScore",
  webDir: "dist",
  server: {
    androidScheme: "https",
    cleartext: true,
  },
}

export default config
