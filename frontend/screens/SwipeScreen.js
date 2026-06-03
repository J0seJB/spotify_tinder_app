import React, { useState, useEffect, useRef } from "react";
import {
  View, Text, StyleSheet, Image, TouchableOpacity, Pressable,
  Animated, PanResponder, Dimensions, ActivityIndicator, Platform
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { API } from "../api";

const { width: W, height: H } = Dimensions.get("window");
const SWIPE_THRESHOLD = W * 0.35;

function formatMs(ms = 0) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export default function SwipeScreen({ route, navigation }) {
  const routeSeeds = route?.params?.seeds || [];
  const source = route?.params?.source || "liked";
  const seedCount = routeSeeds.length;
  const [card, setCard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [remaining, setRemaining] = useState(0);
  const [approved, setApproved] = useState(seedCount);
  const [completion, setCompletion] = useState(null);
  const [completing, setCompleting] = useState(false);
  const [screenError, setScreenError] = useState("");
  const [connectBusy, setConnectBusy] = useState(false);
  const [connectPlaying, setConnectPlaying] = useState(false);
  const [connectDevice, setConnectDevice] = useState(null);
  const [connectMessage, setConnectMessage] = useState("Toca Play para escuchar en Spotify");
  const [connectError, setConnectError] = useState("");
  const [autoplayEnabled, setAutoplayEnabled] = useState(true);
  const [playback, setPlayback] = useState({ progress_ms: 0, duration_ms: 0, is_playing: false });
  const [seeking, setSeeking] = useState(false);

  const pan = useRef(new Animated.ValueXY()).current;
  const progressLayout = useRef({ x: 0, width: 1 });
  const rotate = pan.x.interpolate({ inputRange: [-W, 0, W], outputRange: ["-20deg", "0deg", "20deg"] });
  const likeOpacity = pan.x.interpolate({ inputRange: [0, SWIPE_THRESHOLD / 2], outputRange: [0, 1], extrapolate: "clamp" });
  const nopeOpacity = pan.x.interpolate({ inputRange: [-SWIPE_THRESHOLD / 2, 0], outputRange: [1, 0], extrapolate: "clamp" });

  const panResponder = PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onPanResponderMove: Animated.event([null, { dx: pan.x, dy: pan.y }], { useNativeDriver: false }),
    onPanResponderRelease: (_, gesture) => {
      if (gesture.dx > SWIPE_THRESHOLD) {
        swipe("right");
      } else if (gesture.dx < -SWIPE_THRESHOLD) {
        swipe("left");
      } else {
        Animated.spring(pan, { toValue: { x: 0, y: 0 }, useNativeDriver: false }).start();
      }
    },
  });

  useEffect(() => {
    loadNext();
  }, []);

  useEffect(() => {
    setConnectError("");
    setPlayback({ progress_ms: 0, duration_ms: 0, is_playing: false });
    if (!connectPlaying) setConnectMessage("Toca Play para escuchar en Spotify");
  }, [card?.id]);

  useEffect(() => {
    if (!connectPlaying || !card) return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const current = await API.currentPlayback();
        if (cancelled) return;
        if (!current.track || current.track.id === card.id) {
          setPlayback(current);
          setConnectPlaying(Boolean(current.is_playing));
          if (current.device) setConnectDevice(current.device);
        }
      } catch (_e) {
        // Polling should stay quiet; explicit controls surface errors.
      }
    };
    refresh();
    const timer = setInterval(refresh, 1000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [connectPlaying, card?.id]);

  async function playTrackInSpotify(targetCard = card, silent = false) {
    if (!targetCard || connectBusy) return false;
    setConnectBusy(true);
    setConnectError("");
    if (!silent) setConnectMessage("Buscando dispositivo Spotify...");
    try {
      const res = await API.playTrack({ trackId: targetCard.id, uri: targetCard.uri });
      setConnectDevice(res.device || null);
      setConnectPlaying(true);
      setPlayback({ progress_ms: 0, duration_ms: 0, is_playing: true });
      setConnectMessage(`Reproduciendo en ${(res.device && res.device.name) || "Spotify"}`);
      return true;
    } catch (e) {
      setConnectPlaying(false);
      setConnectError(e.message || "No se pudo reproducir en Spotify");
      setConnectMessage("Abre Spotify en tu celular, PC o Web Player");
      return false;
    } finally {
      setConnectBusy(false);
    }
  }

  async function playCurrentInSpotify() {
    await playTrackInSpotify(card, false);
  }

  async function pauseSpotify(silent = false) {
    if (connectBusy) return;
    setConnectBusy(true);
    try {
      await API.pausePlayback(connectDevice?.id);
      setConnectPlaying(false);
      setPlayback(p => ({ ...p, is_playing: false }));
      if (!silent) setConnectMessage("Spotify pausado");
    } catch (e) {
      if (!silent) setConnectError(e.message || "No se pudo pausar Spotify");
    } finally {
      setConnectBusy(false);
    }
  }

  async function loadNext(showLoader = true) {
    if (showLoader) setLoading(true);
    setScreenError("");
    try {
      const res = await API.getNext(1);
      const cards = res.cards || [];
      const nextCard = cards[0] || null;
      setCard(nextCard);
      setRemaining(res.remaining || 0);
      if (res.completion) setCompletion(res.completion);
      return nextCard;
    } catch (e) {
      setCard(null);
      setScreenError(e.message || "No se pudieron cargar canciones");
      return null;
    } finally {
      if (showLoader) setLoading(false);
    }
  }

  async function swipe(direction) {
    if (!card) return;
    const current = card;
    const isLike = direction === "right";
    const shouldAutoplayNext = connectPlaying && autoplayEnabled;

    Animated.timing(pan, {
      toValue: { x: isLike ? W * 1.5 : -W * 1.5, y: 0 },
      duration: 300, useNativeDriver: false,
    }).start(async () => {
      pan.setValue({ x: 0, y: 0 });
      setCard(null);
      setLoading(true);
      try {
        const feedback = await API.sendFeedback(
          isLike ? [current.id] : [],
          isLike ? [] : [current.id],
        );
        if (typeof feedback.remaining === "number") {
          setRemaining(feedback.remaining);
        }
        if (feedback.completion) setCompletion(feedback.completion);
        if (isLike) setApproved(a => a + 1);
      } catch (e) {
        setScreenError(e.message || "No se pudo guardar tu seleccion");
      }

      if (connectPlaying && !shouldAutoplayNext) pauseSpotify(true);
      const nextCard = await loadNext(false);
      if (shouldAutoplayNext && nextCard) {
        await playTrackInSpotify(nextCard, true);
      }
      setLoading(false);
    });
  }

  async function seekToRatio(ratio) {
    const duration = playback.duration_ms || 0;
    if (!duration || seeking) return;
    const positionMs = Math.round(Math.max(0, Math.min(1, ratio)) * duration);
    setSeeking(true);
    setConnectError("");
    try {
      await API.seekPlayback(positionMs, connectDevice?.id);
      setPlayback(p => ({ ...p, progress_ms: positionMs }));
    } catch (e) {
      setConnectError(e.message || "No se pudo adelantar la cancion");
    } finally {
      setSeeking(false);
    }
  }

  function seekFromEvent(event) {
    const native = event?.nativeEvent || {};
    const width = progressLayout.current.width || 1;
    let x = native.locationX ?? native.offsetX;
    if (typeof x !== "number") {
      x = (native.pageX ?? 0) - (progressLayout.current.x || 0);
    }
    seekToRatio(x / width);
  }

  async function completePlaylist() {
    if (completing) return;
    setCompleting(true);
    setScreenError("");
    try {
      const result = await API.completePlaylist(25);
      setApproved(result.approved_total || approved);
      navigation.replace("Playlist", {
        approved: result.approved_total || approved,
        completed: result.added || 0,
        completedTracks: result.tracks || [],
        seeds: routeSeeds,
        source,
      });
    } catch (e) {
      setScreenError(e.message || "No se pudo completar la playlist");
    } finally {
      setCompleting(false);
    }
  }

  function addMoreSeeds() {
    navigation.replace("SearchSeed", { initialSeeds: routeSeeds, initialSource: source });
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#1DB954" />
        <Text style={styles.loadingText}>Buscando canciones...</Text>
      </View>
    );
  }

  if (!card) {
    const noSuggestions = !screenError && remaining === 0 && approved <= seedCount;
    return (
      <View style={styles.center}>
        <Text style={styles.doneEmoji}>{noSuggestions ? "Sin coincidencias" : "Listo"}</Text>
        <Text style={styles.doneTitle}>
          {noSuggestions ? "No encontre canciones similares" : "Eso es todo"}
        </Text>
        <Text style={styles.doneSubtitle}>
          {screenError || (noSuggestions
            ? "Las semillas son validas, pero con las canciones disponibles no hubo coincidencias suficientemente cercanas. Agrega una o dos canciones mas parecidas para ampliar el perfil."
            : `${approved} canciones aprobadas`)}
        </Text>
        {noSuggestions ? (
          <TouchableOpacity style={[styles.btn, styles.secondaryBtn]} onPress={addMoreSeeds}>
            <Text style={styles.secondaryBtnText}>Agregar mas semillas</Text>
          </TouchableOpacity>
        ) : null}
        <TouchableOpacity
          style={[styles.btn, noSuggestions && styles.quietBtn]}
          onPress={() => navigation.navigate("Playlist", { approved, seeds: routeSeeds, source })}
        >
          <Text style={[styles.btnText, noSuggestions && styles.quietBtnText]}>Crear playlist</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {card?.image_url && (
        <View style={StyleSheet.absoluteFill}>
          <Image
            source={{ uri: card.image_url }}
            style={styles.backgroundImage}
            blurRadius={50}
          />
          <View style={styles.backgroundOverlay} />
        </View>
      )}

      <SafeAreaView style={{ flex: 1 }}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.navigate("Playlist", { approved, seeds: routeSeeds, source })}>
            <Text style={styles.headerLink}>Crear playlist ({approved})</Text>
          </TouchableOpacity>
          {completion?.can_complete ? (
            <TouchableOpacity
              style={[styles.completeHeaderBtn, completing && styles.completeHeaderBtnDisabled]}
              onPress={completePlaylist}
              disabled={completing}
            >
              {completing
                ? <ActivityIndicator size="small" color="#000" />
                : <Text style={styles.completeHeaderText}>Completar</Text>
              }
            </TouchableOpacity>
          ) : null}
          <Text style={styles.headerCount}>{remaining} restantes</Text>
        </View>

        {screenError ? <Text style={styles.screenError}>{screenError}</Text> : null}

        <View style={styles.cardArea}>
          <Animated.View
            style={[styles.card, { transform: [{ translateX: pan.x }, { translateY: pan.y }, { rotate }] }]}
            {...panResponder.panHandlers}
          >
            {card.image_url
              ? <Image source={{ uri: card.image_url }} style={styles.cardImage} />
              : <View style={[styles.cardImage, styles.noImage]}><Text style={styles.noImageText}>Music</Text></View>
            }
            <LinearGradient colors={["transparent", "rgba(0,0,0,0.95)"]} style={styles.cardGradient}>
              <Text style={styles.cardTitle} numberOfLines={2}>{card.name}</Text>
              <Text style={styles.cardArtist} numberOfLines={1}>{card.artists}</Text>
              {card.album ? <Text style={styles.cardAlbum} numberOfLines={1}>{card.album}</Text> : null}

              <View style={styles.connectPanel}>
                <View style={styles.connectMain}>
                  <View style={styles.connectTopRow}>
                    <View style={styles.connectCopy}>
                      <Text style={styles.connectTitle} numberOfLines={1}>
                        {connectPlaying ? "Spotify Connect activo" : "Spotify Connect"}
                      </Text>
                      <Text
                        style={[styles.connectSubtitle, connectError ? styles.connectError : null]}
                        numberOfLines={2}
                      >
                        {connectError || connectMessage}
                      </Text>
                    </View>
                    <TouchableOpacity
                      style={[styles.autoplayToggle, autoplayEnabled && styles.autoplayToggleOn]}
                      onPress={() => setAutoplayEnabled(v => !v)}
                    >
                      <Text style={[styles.autoplayToggleText, autoplayEnabled && styles.autoplayToggleTextOn]}>
                        Auto
                      </Text>
                    </TouchableOpacity>
                  </View>
                  <Pressable
                    activeOpacity={0.85}
                    style={[styles.progressTrack, (!playback.duration_ms || seeking) && styles.progressTrackDisabled]}
                    onLayout={event => {
                      const layout = event.nativeEvent.layout || {};
                      progressLayout.current = {
                        x: layout.x || progressLayout.current.x || 0,
                        width: layout.width || 1,
                      };
                    }}
                    onPressIn={seekFromEvent}
                    disabled={!playback.duration_ms || seeking}
                  >
                    <View
                      style={[
                        styles.progressFill,
                        { width: `${Math.min(100, ((playback.progress_ms || 0) / Math.max(1, playback.duration_ms || 1)) * 100)}%` },
                      ]}
                    />
                  </Pressable>
                  <View style={styles.progressTimes}>
                    <Text style={styles.progressTime}>{formatMs(playback.progress_ms)}</Text>
                    <Text style={styles.progressTime}>{formatMs(playback.duration_ms)}</Text>
                  </View>
                </View>
                <TouchableOpacity
                  style={[styles.connectBtn, connectPlaying && styles.connectBtnPause, connectBusy && styles.connectBtnDisabled]}
                  onPress={connectPlaying ? () => pauseSpotify(false) : playCurrentInSpotify}
                  disabled={connectBusy}
                >
                  {connectBusy
                    ? <ActivityIndicator size="small" color="#000" />
                    : <Text style={styles.connectBtnText}>{connectPlaying ? "Pausar" : "Play"}</Text>
                  }
                </TouchableOpacity>
              </View>
            </LinearGradient>

            <Animated.View style={[styles.badge, styles.badgeLike, { opacity: likeOpacity }]}>
              <Text style={styles.badgeText}>LIKE</Text>
            </Animated.View>
            <Animated.View style={[styles.badge, styles.badgeNope, { opacity: nopeOpacity }]}>
              <Text style={styles.badgeText}>NOPE</Text>
            </Animated.View>
          </Animated.View>
        </View>

        <View style={styles.buttons}>
          <TouchableOpacity style={[styles.circleBtn, styles.nopeBtn]} onPress={() => swipe("left")}>
            <Text style={styles.nopeBtnText}>X</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.circleBtn, styles.likeBtn]} onPress={() => swipe("right")}>
            <Text style={styles.likeBtnText}>OK</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    </View>
  );
}

const CARD_W = Platform.OS === "web" ? Math.min(520, Math.max(360, W * 0.36)) : W - 32;
const CARD_H = Platform.OS === "web" ? Math.min(700, Math.max(520, H * 0.74)) : H * 0.62;

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0a0a" },
  backgroundImage: {
    ...StyleSheet.absoluteFillObject,
    width: "100%",
    height: "100%",
    resizeMode: "cover",
    transform: [{ scale: 1.25 }],
  },
  backgroundOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.6)",
  },
  center: { flex: 1, backgroundColor: "#0a0a0a", justifyContent: "center", alignItems: "center", padding: 32 },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    alignSelf: "center",
    width: "100%",
    maxWidth: Platform.OS === "web" ? 920 : undefined,
    paddingHorizontal: Platform.OS === "web" ? 32 : 20,
    paddingTop: Platform.OS === "web" ? 24 : 12,
    paddingBottom: 8,
  },
  headerLink: { color: "#1DB954", fontSize: 14, fontWeight: "700" },
  completeHeaderBtn: {
    backgroundColor: "#1DB954",
    borderRadius: 999,
    minWidth: 104,
    minHeight: 36,
    paddingHorizontal: 16,
    justifyContent: "center",
    alignItems: "center",
  },
  completeHeaderBtnDisabled: { opacity: 0.7 },
  completeHeaderText: { color: "#000", fontSize: 13, fontWeight: "900" },
  headerCount: { color: "#777", fontSize: 14 },
  screenError: { color: "#ff9aa7", textAlign: "center", paddingHorizontal: 20, marginTop: 4 },
  cardArea: { flex: 1, alignItems: "center", justifyContent: "center", minHeight: Platform.OS === "web" ? 560 : undefined },
  card: {
    position: "absolute", width: CARD_W, height: CARD_H,
    borderRadius: 24, overflow: "hidden",
    shadowColor: "#000", shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.5, shadowRadius: 16, elevation: 12,
  },
  cardImage: { width: "100%", height: "100%", backgroundColor: "#1a1a1a" },
  noImage: { justifyContent: "center", alignItems: "center" },
  noImageText: { fontSize: 34, fontWeight: "900", color: "#333" },
  cardGradient: {
    position: "absolute", bottom: 0, left: 0, right: 0,
    paddingHorizontal: 20, paddingBottom: 24, paddingTop: 60,
  },
  cardTitle: { fontSize: 26, fontWeight: "800", color: "#fff", lineHeight: 32 },
  cardArtist: { fontSize: 16, color: "#ccc", marginTop: 4 },
  cardAlbum: { fontSize: 13, color: "#888", marginTop: 2 },
  connectPanel: {
    marginTop: 14,
    minHeight: 98,
    backgroundColor: "rgba(255,255,255,0.12)",
    borderColor: "rgba(255,255,255,0.18)",
    borderWidth: 1,
    borderRadius: 16,
    paddingVertical: 10,
    paddingHorizontal: 12,
    flexDirection: "row",
    alignItems: "stretch",
    gap: 10,
  },
  connectMain: { flex: 1, minWidth: 0 },
  connectTopRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  connectCopy: { flex: 1, minWidth: 0 },
  connectTitle: { color: "#fff", fontSize: 13, fontWeight: "800" },
  connectSubtitle: { color: "#cfcfcf", fontSize: 11, marginTop: 2, lineHeight: 15 },
  connectError: { color: "#ff9aa7" },
  autoplayToggle: {
    minWidth: 52,
    height: 30,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.18)",
    justifyContent: "center",
    alignItems: "center",
  },
  autoplayToggleOn: { backgroundColor: "#1DB954", borderColor: "#1DB954" },
  autoplayToggleText: { color: "#cfcfcf", fontSize: 11, fontWeight: "900" },
  autoplayToggleTextOn: { color: "#000" },
  progressTrack: {
    height: 12,
    borderRadius: 6,
    backgroundColor: "rgba(255,255,255,0.18)",
    marginTop: 10,
    overflow: "hidden",
  },
  progressTrackDisabled: { opacity: 0.55 },
  progressFill: {
    height: "100%",
    borderRadius: 6,
    backgroundColor: "#1DB954",
  },
  progressTimes: { flexDirection: "row", justifyContent: "space-between", marginTop: 5 },
  progressTime: { color: "#aaa", fontSize: 10, fontWeight: "700" },
  connectBtn: {
    minWidth: 72,
    height: 38,
    borderRadius: 19,
    backgroundColor: "#1DB954",
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 14,
    alignSelf: "center",
  },
  connectBtnPause: { backgroundColor: "#fff" },
  connectBtnDisabled: { opacity: 0.65 },
  connectBtnText: { color: "#000", fontWeight: "900", fontSize: 13 },
  badge: {
    position: "absolute", top: 40, paddingHorizontal: 16, paddingVertical: 8,
    borderWidth: 3, borderRadius: 8,
  },
  badgeLike: { left: 20, borderColor: "#1DB954", transform: [{ rotate: "-15deg" }] },
  badgeNope: { right: 20, borderColor: "#ff4458", transform: [{ rotate: "15deg" }] },
  badgeText: { fontSize: 28, fontWeight: "900", color: "#fff" },
  buttons: { flexDirection: "row", justifyContent: "center", gap: 32, paddingBottom: Platform.OS === "web" ? 40 : 32, paddingTop: 16 },
  circleBtn: { width: 68, height: 68, borderRadius: 34, justifyContent: "center", alignItems: "center", elevation: 6 },
  nopeBtn: { backgroundColor: "#1a1a1a", borderWidth: 2, borderColor: "#ff4458" },
  nopeBtnText: { fontSize: 18, fontWeight: "900", color: "#ff4458" },
  likeBtn: { backgroundColor: "#1DB954" },
  likeBtnText: { fontSize: 15, fontWeight: "900", color: "#000" },
  loadingText: { color: "#888", marginTop: 16, fontSize: 15 },
  doneEmoji: { color: "#1DB954", fontSize: 18, fontWeight: "900", marginBottom: 16 },
  doneTitle: { fontSize: 28, fontWeight: "800", color: "#fff" },
  doneSubtitle: { fontSize: 16, color: "#888", marginTop: 8, marginBottom: 32, textAlign: "center" },
  btn: { backgroundColor: "#1DB954", borderRadius: 14, paddingHorizontal: 32, paddingVertical: 16 },
  secondaryBtn: { marginBottom: 12, minWidth: 220, alignItems: "center" },
  secondaryBtnText: { color: "#000", fontSize: 16, fontWeight: "800" },
  quietBtn: { backgroundColor: "#1a1a1a", borderWidth: 1, borderColor: "#333", minWidth: 220, alignItems: "center" },
  quietBtnText: { color: "#aaa" },
  btnText: { color: "#000", fontSize: 16, fontWeight: "800" }
});
