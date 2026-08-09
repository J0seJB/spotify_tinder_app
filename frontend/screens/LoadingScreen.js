import React, { useEffect, useRef, useState } from "react";
import { Text, StyleSheet, ActivityIndicator, Animated, TouchableOpacity } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { API } from "../api";

export default function LoadingScreen({ navigation }) {
  const [status, setStatus] = useState("Conectando...");
  const fadeAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 800,
      useNativeDriver: true,
    }).start();

    // If Spotify returned an access token via the URL fragment (after /callback redirect), capture it
    try {
      if (typeof window !== 'undefined' && window.location && window.location.hash) {
        const m = window.location.hash.match(/access_token=([^&]+)/);
        if (m && m[1]) {
          const token = decodeURIComponent(m[1]);
          // set token for API calls
          const { setAccessToken } = require("../api");
          setAccessToken(token);
          // remove hash from URL
          history.replaceState(null, '', window.location.pathname + window.location.search);
        }
      }
    } catch (err) {
      // ignore
    }

    loadTracks();
  }, []);

  async function loadTracks() {
    try {
      setStatus("Conectando con Spotify...");
      const res = await API.load(3452);
      if (res.ok) {
        setStatus(`${res.total} canciones listas`);
        setTimeout(() => navigation.replace("SearchSeed"), 1000);
      } else {
        setStatus("No se pudo cargar la biblioteca.");
      }
    } catch (e) {
      setStatus("Error conectando. Esta corriendo el servidor?");
    }
  }

  return (
    <LinearGradient colors={["#0a0a0a", "#1a0a2e", "#0a0a0a"]} style={styles.container}>
      <Animated.View style={[styles.content, { opacity: fadeAnim }]}>
        <Text style={styles.logo}>Music</Text>
        <Text style={styles.title}>Spotify Tinder</Text>
        <Text style={styles.subtitle}>Descubre tu proxima playlist</Text>
        <ActivityIndicator size="large" color="#1DB954" style={{ marginTop: 40 }} />
        <Text style={styles.status}>{status}</Text>
      </Animated.View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", alignItems: "center" },
  content: { alignItems: "center", paddingHorizontal: 40 },
  logo: { fontSize: 44, fontWeight: "900", color: "#1DB954", marginBottom: 16 },
  title: { fontSize: 32, fontWeight: "800", color: "#fff", letterSpacing: 1 },
  subtitle: { fontSize: 16, color: "#888", marginTop: 8 },
  status: { fontSize: 14, color: "#1DB954", marginTop: 20, textAlign: "center" },
});
