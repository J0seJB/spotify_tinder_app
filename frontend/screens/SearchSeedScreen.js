import React, { useState } from "react";
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  StyleSheet, ActivityIndicator, Platform
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { API } from "../api";

export default function SearchSeedScreen({ navigation }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [seeds, setSeeds] = useState([]);
  const [searchError, setSearchError] = useState("");
  const [analyzing, setAnalyzing] = useState(false);

  async function search(text) {
    setQuery(text);
    setSearchError("");
    if (text.length < 2) {
      setResults([]);
      return;
    }
    try {
      const res = await API.search(text);
      setResults(res.results || []);
    } catch (e) {
      setResults([]);
      setSearchError(e.message || "No se pudo buscar");
    }
  }

  function toggleSeed(track) {
    const exists = seeds.find(s => s.id === track.id);
    if (exists) {
      setSeeds(seeds.filter(s => s.id !== track.id));
    } else {
      setSeeds([...seeds, track]);
    }
  }

  async function startSwiping() {
    if (seeds.length === 0) return;
    setAnalyzing(true);
    setSearchError("");
    try {
      await API.setSeeds(seeds.map(s => s.id));
      navigation.replace("Swipe", { seeds });
    } catch (e) {
      setSearchError(e.message || "No se pudo analizar la seleccion");
      setAnalyzing(false);
    }
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.title}>Elige tus semillas</Text>
        <Text style={styles.subtitle}>Canciones que definen el vibe de tu playlist</Text>

        <TextInput
          style={styles.input}
          placeholder="Busca una cancion o artista..."
          placeholderTextColor="#555"
          value={query}
          onChangeText={search}
        />

        {searchError ? <Text style={styles.error}>{searchError}</Text> : null}

        {seeds.length > 0 && (
          <View style={styles.seedsRow}>
            {seeds.map(s => (
              <TouchableOpacity key={s.id} onPress={() => toggleSeed(s)} style={styles.seedChip}>
                <Text style={styles.seedChipText} numberOfLines={1}>{s.name}</Text>
                <Text style={styles.seedChipX}>x</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        <FlatList
          data={results}
          keyExtractor={item => item.id}
          renderItem={({ item }) => {
            const selected = seeds.find(s => s.id === item.id);
            return (
              <TouchableOpacity
                style={[styles.result, selected && styles.resultSelected]}
                onPress={() => toggleSeed(item)}
              >
                <View style={styles.resultLeft}>
                  <Text style={styles.resultName} numberOfLines={1}>{item.name}</Text>
                  <Text style={styles.resultArtist} numberOfLines={1}>{item.artists}</Text>
                </View>
                {selected && <Text style={styles.checkmark}>OK</Text>}
              </TouchableOpacity>
            );
          }}
          style={styles.list}
        />

        {seeds.length > 0 && (
          <TouchableOpacity
            style={[styles.btn, analyzing && styles.btnDisabled]}
            onPress={startSwiping}
            disabled={analyzing}
          >
            {analyzing
              ? <ActivityIndicator color="#000" />
              : <Text style={styles.btnText}>Analizar y empezar</Text>
            }
          </TouchableOpacity>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0a0a0a",
    paddingHorizontal: Platform.OS === "web" ? 40 : 20,
    alignItems: Platform.OS === "web" ? "center" : "stretch",
  },
  content: {
    flex: 1,
    width: "100%",
    maxWidth: Platform.OS === "web" ? 760 : undefined,
  },
  title: { fontSize: Platform.OS === "web" ? 34 : 26, fontWeight: "800", color: "#fff", marginTop: Platform.OS === "web" ? 44 : 20 },
  subtitle: { fontSize: 14, color: "#666", marginBottom: 20 },
  input: {
    backgroundColor: "#1a1a1a", borderRadius: 12, padding: 14,
    color: "#fff", fontSize: 16, marginBottom: 12,
    borderWidth: 1, borderColor: "#2a2a2a",
  },
  error: { color: "#ff9aa7", fontSize: 13, marginBottom: 12 },
  seedsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 12 },
  seedChip: {
    flexDirection: "row", alignItems: "center", backgroundColor: "#1DB95422",
    borderColor: "#1DB954", borderWidth: 1, borderRadius: 20,
    paddingHorizontal: 12, paddingVertical: 6, maxWidth: 160,
  },
  seedChipText: { color: "#1DB954", fontSize: 12, flex: 1 },
  seedChipX: { color: "#1DB954", fontSize: 16, marginLeft: 4 },
  list: { flex: 1 },
  result: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    backgroundColor: "#141414", borderRadius: 12, padding: 14, marginBottom: 8,
    borderWidth: 1, borderColor: "#1e1e1e",
  },
  resultSelected: { borderColor: "#1DB954", backgroundColor: "#1DB95411" },
  resultLeft: { flex: 1 },
  resultName: { color: "#fff", fontSize: 15, fontWeight: "600" },
  resultArtist: { color: "#888", fontSize: 13, marginTop: 2 },
  checkmark: { color: "#1DB954", fontSize: 12, fontWeight: "900", marginLeft: 12 },
  btn: {
    backgroundColor: "#1DB954", borderRadius: 14, padding: 18,
    alignItems: "center", marginVertical: 16,
  },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: "#000", fontSize: 16, fontWeight: "800" },
});
