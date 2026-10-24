import React, { useEffect, useState } from "react";
import {
  View, Text, TextInput, TouchableOpacity, FlatList, Image,
  StyleSheet, ActivityIndicator,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { API } from "../api";
import SpotifyPlayer from "../components/SpotifyPlayer";

const PAGE_SIZE = 50;

export default function SearchSeedScreen({ navigation }) {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("library");
  const [results, setResults] = useState([]);
  const [seeds, setSeeds] = useState([]);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [playingTrack, setPlayingTrack] = useState(null);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    loadLibrary();
  }, []);

  async function loadLibrary(pageOffset = 0, append = false) {
    setLoading(true);
    setError("");
    try {
      const response = await API.library(pageOffset, PAGE_SIZE);
      if (response.detail) throw new Error(response.detail);
      setResults(current => append ? [...current, ...(response.results || [])] : response.results || []);
      setOffset(pageOffset + (response.results || []).length);
      setTotal(response.total || 0);
    } catch (e) {
      setError(e.message || "No se pudo cargar tu biblioteca.");
    } finally {
      setLoading(false);
    }
  }

  async function search(text, searchSource = source) {
    setQuery(text);
    setError("");
    if (searchSource === "library" && text.trim().length < 2) {
      await loadLibrary();
      return;
    }
    if (text.trim().length < 2) {
      setResults([]);
      return;
    }

    setLoading(true);
    try {
      const response = searchSource === "spotify"
        ? await API.searchSpotify(text)
        : await API.search(text);
      if (response.detail) throw new Error(response.detail);
      setResults(response.results || []);
      setOffset(0);
      setTotal(0);
    } catch (e) {
      setError(e.message || "No se pudo buscar la canción.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  function changeSource(nextSource) {
    setSource(nextSource);
    setQuery("");
    setError("");
    setResults([]);
    setPlayingTrack(null);
    if (nextSource === "library") {
      loadLibrary();
    }
  }

  function toggleSeed(track) {
    setSeeds(current => current.some(seed => seed.id === track.id)
      ? current.filter(seed => seed.id !== track.id)
      : [...current, track]);
  }

  async function startSwiping() {
    if (seeds.length === 0) return;
    setAnalyzing(true);
    setError("");
    try {
      const response = await API.setSeeds(seeds.map(seed => seed.id));
      if (!response.ok) throw new Error(response.detail || "No se pudieron analizar las semillas.");
      navigation.replace("Swipe", { seeds });
    } catch (e) {
      setError(e.message || "No se pudieron analizar las canciones seleccionadas.");
      setAnalyzing(false);
    }
  }

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.title}>Elige tus semillas</Text>
      <Text style={styles.subtitle}>Elige de tu biblioteca o busca cualquier canción en Spotify.</Text>

      <View style={styles.tabs}>
        <TouchableOpacity
          accessibilityRole="button"
          style={[styles.tab, source === "library" && styles.tabSelected]}
          onPress={() => changeSource("library")}
        >
          <Text style={[styles.tabText, source === "library" && styles.tabTextSelected]}>Mi biblioteca</Text>
        </TouchableOpacity>
        <TouchableOpacity
          accessibilityRole="button"
          style={[styles.tab, source === "spotify" && styles.tabSelected]}
          onPress={() => changeSource("spotify")}
        >
          <Text style={[styles.tabText, source === "spotify" && styles.tabTextSelected]}>Buscar en Spotify</Text>
        </TouchableOpacity>
      </View>

      <TextInput
        style={styles.input}
        placeholder={source === "library" ? "Filtra tu biblioteca..." : "Busca una canción o artista..."}
        placeholderTextColor="#777"
        value={query}
        onChangeText={text => search(text)}
      />

      {seeds.length > 0 && (
        <View style={styles.seedsRow}>
          {seeds.map(seed => (
            <TouchableOpacity key={seed.id} onPress={() => toggleSeed(seed)} style={styles.seedChip}>
              <Text style={styles.seedChipText} numberOfLines={1}>{seed.name}</Text>
              <Text style={styles.seedChipX}>×</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {error ? <Text style={styles.error}>{error}</Text> : null}
      {source === "spotify" && query.trim().length < 2 && !loading ? (
        <Text style={styles.helper}>Escribe al menos 2 caracteres para buscar en todo Spotify.</Text>
      ) : null}

      <FlatList
        data={results}
        keyExtractor={item => item.id}
        style={styles.list}
        renderItem={({ item }) => {
          const selected = seeds.some(seed => seed.id === item.id);
          const isPlaying = playingTrack?.id === item.id;
          return (
            <View style={[styles.result, selected && styles.resultSelected]}>
              {item.image_url
                ? <Image source={{ uri: item.image_url }} style={styles.resultImage} />
                : <View style={[styles.resultImage, styles.noImage]}><Text style={styles.noImageText}>♫</Text></View>
              }
              <TouchableOpacity
                accessibilityRole="button"
                style={styles.resultInfo}
                onPress={() => toggleSeed(item)}
              >
                <Text style={styles.resultName} numberOfLines={1}>{item.name}</Text>
                <Text style={styles.resultArtist} numberOfLines={1}>{item.artists}</Text>
                {item.in_library ? <Text style={styles.libraryLabel}>En Me gusta</Text> : null}
              </TouchableOpacity>
              <View style={styles.resultActions}>
                <TouchableOpacity
                  accessibilityRole="button"
                  style={[styles.smallButton, isPlaying && styles.smallButtonActive]}
                  onPress={() => setPlayingTrack(isPlaying ? null : item)}
                >
                  <Text style={styles.smallButtonText}>{isPlaying ? "⏸" : "▶"}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  accessibilityRole="button"
                  style={[styles.selectButton, selected && styles.selectButtonSelected]}
                  onPress={() => toggleSeed(item)}
                >
                  <Text style={styles.selectButtonText}>{selected ? "✓" : "+"}</Text>
                </TouchableOpacity>
              </View>
            </View>
          );
        }}
        ListEmptyComponent={loading
          ? <ActivityIndicator color="#1DB954" style={styles.loading} />
          : source === "library" && !error
            ? <Text style={styles.helper}>No encontramos canciones en tu biblioteca con esa búsqueda.</Text>
            : null
        }
        ListFooterComponent={source === "library" && !query && offset < total
          ? (
            <TouchableOpacity style={styles.moreButton} onPress={() => loadLibrary(offset, true)} disabled={loading}>
              <Text style={styles.moreButtonText}>{loading ? "Cargando..." : `Cargar más (${offset}/${total})`}</Text>
            </TouchableOpacity>
          )
          : null
        }
      />

      {playingTrack ? (
        <View style={styles.player}>
          <Text style={styles.playerTitle} numberOfLines={1}>
            Escuchando: {playingTrack.name} — {playingTrack.artists}
          </Text>
          <SpotifyPlayer trackId={playingTrack.id} />
        </View>
      ) : null}

      {seeds.length > 0 && (
        <TouchableOpacity
          style={[styles.btn, analyzing && styles.btnDisabled]}
          onPress={startSwiping}
          disabled={analyzing}
        >
          {analyzing
            ? <ActivityIndicator color="#000" />
            : <Text style={styles.btnText}>Analizar y empezar ({seeds.length}) →</Text>
          }
        </TouchableOpacity>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0a0a", paddingHorizontal: 20 },
  title: { fontSize: 26, fontWeight: "800", color: "#fff", marginTop: 12 },
  subtitle: { fontSize: 14, color: "#999", marginBottom: 12 },
  tabs: { flexDirection: "row", gap: 8, marginBottom: 12 },
  tab: { flex: 1, borderRadius: 10, padding: 11, alignItems: "center", backgroundColor: "#1a1a1a" },
  tabSelected: { backgroundColor: "#1DB954" },
  tabText: { color: "#bbb", fontWeight: "700", fontSize: 13 },
  tabTextSelected: { color: "#000" },
  input: {
    backgroundColor: "#1a1a1a", borderRadius: 12, padding: 14,
    color: "#fff", fontSize: 16, marginBottom: 10,
    borderWidth: 1, borderColor: "#2a2a2a",
  },
  seedsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 10 },
  seedChip: {
    flexDirection: "row", alignItems: "center", backgroundColor: "#1DB95422",
    borderColor: "#1DB954", borderWidth: 1, borderRadius: 20,
    paddingHorizontal: 12, paddingVertical: 6, maxWidth: 160,
  },
  seedChipText: { color: "#1DB954", fontSize: 12, flex: 1 },
  seedChipX: { color: "#1DB954", fontSize: 16, marginLeft: 4 },
  list: { flex: 1 },
  result: {
    flexDirection: "row", alignItems: "center", backgroundColor: "#141414",
    borderRadius: 12, padding: 9, marginBottom: 8,
    borderWidth: 1, borderColor: "#1e1e1e",
  },
  resultSelected: { borderColor: "#1DB954", backgroundColor: "#1DB95411" },
  resultImage: { width: 48, height: 48, borderRadius: 6, marginRight: 10, backgroundColor: "#222" },
  noImage: { alignItems: "center", justifyContent: "center" },
  noImageText: { color: "#888", fontSize: 24 },
  resultInfo: { flex: 1, paddingVertical: 4 },
  resultName: { color: "#fff", fontSize: 14, fontWeight: "600" },
  resultArtist: { color: "#aaa", fontSize: 12, marginTop: 2 },
  libraryLabel: { color: "#1DB954", fontSize: 10, marginTop: 2 },
  resultActions: { flexDirection: "row", gap: 8, marginLeft: 8 },
  smallButton: { width: 36, height: 36, borderRadius: 18, backgroundColor: "#252525", alignItems: "center", justifyContent: "center" },
  smallButtonActive: { backgroundColor: "#1DB954" },
  smallButtonText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  selectButton: { width: 36, height: 36, borderRadius: 18, borderColor: "#1DB954", borderWidth: 1, alignItems: "center", justifyContent: "center" },
  selectButtonSelected: { backgroundColor: "#1DB954" },
  selectButtonText: { color: "#fff", fontSize: 21, fontWeight: "700" },
  loading: { marginTop: 24 },
  helper: { color: "#888", textAlign: "center", padding: 14 },
  error: { color: "#ff7070", marginVertical: 6 },
  moreButton: { padding: 14, alignItems: "center", marginBottom: 8 },
  moreButtonText: { color: "#1DB954", fontWeight: "700" },
  player: { marginTop: 8, marginBottom: 4 },
  playerTitle: { color: "#ddd", fontSize: 12, marginBottom: 4 },
  btn: { backgroundColor: "#1DB954", borderRadius: 14, padding: 16, alignItems: "center", marginVertical: 12 },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: "#000", fontSize: 16, fontWeight: "800" },
});
