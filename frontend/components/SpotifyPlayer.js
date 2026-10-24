import React, { createElement } from "react";
import { Linking, Platform, StyleSheet, Text, TouchableOpacity, View } from "react-native";

export default function SpotifyPlayer({ trackId }) {
  if (!trackId) return null;

  const trackUrl = `https://open.spotify.com/track/${encodeURIComponent(trackId)}`;
  if (Platform.OS === "web") {
    return createElement("iframe", {
      key: trackId,
      title: "Reproductor de Spotify",
      src: `https://open.spotify.com/embed/track/${encodeURIComponent(trackId)}?utm_source=generator&theme=0`,
      width: "100%",
      height: "80",
      frameBorder: "0",
      allow: "autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture",
      loading: "lazy",
      style: { border: 0, borderRadius: 12 },
    });
  }

  return (
    <TouchableOpacity
      accessibilityRole="button"
      onPress={() => Linking.openURL(trackUrl)}
      style={styles.nativeLink}
    >
      <Text style={styles.nativeLinkText}>▶ Escuchar en Spotify</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  nativeLink: {
    backgroundColor: "#1DB954",
    borderRadius: 12,
    padding: 14,
    alignItems: "center",
  },
  nativeLinkText: { color: "#000", fontWeight: "700" },
});
