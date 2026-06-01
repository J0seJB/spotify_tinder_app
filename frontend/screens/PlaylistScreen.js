import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { API } from "../api";

export default function PlaylistScreen({ route, navigation }) {
  const { approved = 0 } = route.params || {};
  const [name, setName] = useState("Mi playlist IA");
  const [isPublic, setIsPublic] = useState(false);
  const [creating, setCreating] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function create() {
    if (!name.trim()) return;
    setCreating(true);
    setError("");
    try {
      await API.createPlaylist(name.trim(), isPublic);
      setDone(true);
    } catch (e) {
      setError(e.message || "No se pudo crear la playlist");
    } finally {
      setCreating(false);
    }
  }

  async function startOver() {
    await API.reset();
    navigation.replace("SearchSeed");
  }

  if (done) {
    return (
      <LinearGradient colors={["#0a0a0a", "#0a2a15"]} style={styles.center}>
        <Text style={styles.doneEmoji}>OK</Text>
        <Text style={styles.doneTitle}>Playlist creada</Text>
        <Text style={styles.doneSub}>{name} ya esta en Spotify</Text>
        <TouchableOpacity style={styles.btn} onPress={startOver}>
          <Text style={styles.btnText}>Crear otra playlist</Text>
        </TouchableOpacity>
      </LinearGradient>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.title}>Guardar playlist</Text>
      <Text style={styles.subtitle}>{approved} canciones seleccionadas</Text>

      <Text style={styles.label}>Nombre</Text>
      <TextInput
        style={styles.input}
        value={name}
        onChangeText={setName}
        placeholderTextColor="#555"
        maxLength={60}
      />

      <TouchableOpacity style={styles.toggleRow} onPress={() => setIsPublic(!isPublic)}>
        <View style={[styles.toggle, isPublic && styles.toggleOn]}>
          <View style={[styles.toggleThumb, isPublic && styles.toggleThumbOn]} />
        </View>
        <Text style={styles.toggleLabel}>{isPublic ? "Publica" : "Privada"}</Text>
      </TouchableOpacity>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <TouchableOpacity
        style={[styles.btn, creating && styles.btnDisabled]}
        onPress={create}
        disabled={creating}
      >
        {creating
          ? <ActivityIndicator color="#000" />
          : <Text style={styles.btnText}>Crear en Spotify</Text>
        }
      </TouchableOpacity>

      <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
        <Text style={styles.backBtnText}>Seguir swipeando</Text>
      </TouchableOpacity>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0a0a", padding: 24 },
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 32 },
  title: { fontSize: 28, fontWeight: "800", color: "#fff", marginBottom: 4 },
  subtitle: { fontSize: 15, color: "#888", marginBottom: 32 },
  label: { color: "#aaa", fontSize: 13, marginBottom: 8, textTransform: "uppercase", letterSpacing: 1 },
  input: {
    backgroundColor: "#1a1a1a", borderRadius: 12, padding: 16,
    color: "#fff", fontSize: 18, fontWeight: "600", marginBottom: 20,
    borderWidth: 1, borderColor: "#2a2a2a",
  },
  toggleRow: { flexDirection: "row", alignItems: "center", marginBottom: 32 },
  toggle: {
    width: 48, height: 26, borderRadius: 13, backgroundColor: "#2a2a2a",
    justifyContent: "center", paddingHorizontal: 3,
  },
  toggleOn: { backgroundColor: "#1DB95444" },
  toggleThumb: { width: 20, height: 20, borderRadius: 10, backgroundColor: "#555" },
  toggleThumbOn: { backgroundColor: "#1DB954", alignSelf: "flex-end" },
  toggleLabel: { color: "#aaa", fontSize: 15, marginLeft: 12 },
  error: { color: "#ff4458", marginBottom: 16, fontSize: 14 },
  btn: {
    backgroundColor: "#1DB954", borderRadius: 14,
    padding: 18, alignItems: "center", marginBottom: 16,
  },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: "#000", fontSize: 17, fontWeight: "800" },
  backBtn: { alignItems: "center", padding: 12 },
  backBtnText: { color: "#777", fontSize: 15 },
  doneEmoji: { fontSize: 18, fontWeight: "900", color: "#1DB954", marginBottom: 20 },
  doneTitle: { fontSize: 30, fontWeight: "800", color: "#fff", marginBottom: 8 },
  doneSub: { fontSize: 16, color: "#888", marginBottom: 40, textAlign: "center" },
});
