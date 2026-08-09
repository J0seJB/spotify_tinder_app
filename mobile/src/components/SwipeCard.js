// src/components/SwipeCard.js
import React, { useRef, useEffect, useState } from 'react';
import {
  View, Text, Image, StyleSheet, Dimensions,
  Animated, PanResponder, TouchableOpacity, ActivityIndicator,
} from 'react-native';
import { Audio } from 'expo-av';
import { LinearGradient } from 'expo-linear-gradient';

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');
const CARD_W = SCREEN_W * 0.88;
const CARD_H = SCREEN_H * 0.62;
const SWIPE_THRESHOLD = SCREEN_W * 0.3;

export default function SwipeCard({ card, onSwipeRight, onSwipeLeft, isTop }) {
  const position = useRef(new Animated.ValueXY()).current;
  const [sound, setSound] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [imageLoading, setImageLoading] = useState(true);

  // Auto-play preview cuando es la carta de arriba
  useEffect(() => {
    if (isTop && card.preview_url) {
      playPreview();
    }
    return () => {
      if (sound) {
        sound.unloadAsync();
      }
    };
  }, [isTop, card.id]);

  const playPreview = async () => {
    try {
      if (sound) {
        await sound.unloadAsync();
      }
      await Audio.setAudioModeAsync({ playsInSilentModeIOS: true });
      const { sound: newSound } = await Audio.Sound.createAsync(
        { uri: card.preview_url },
        { shouldPlay: true, volume: 0.7 }
      );
      setSound(newSound);
      setPlaying(true);
      newSound.setOnPlaybackStatusUpdate((status) => {
        if (status.didJustFinish) setPlaying(false);
      });
    } catch (e) {
      console.log('Preview no disponible:', e);
    }
  };

  const togglePlay = async () => {
    if (!card.preview_url) return;
    if (playing) {
      await sound?.pauseAsync();
      setPlaying(false);
    } else {
      await playPreview();
    }
  };

  const stopSound = async () => {
    if (sound) {
      await sound.unloadAsync();
      setSound(null);
      setPlaying(false);
    }
  };

  const rotate = position.x.interpolate({
    inputRange: [-SCREEN_W, 0, SCREEN_W],
    outputRange: ['-15deg', '0deg', '15deg'],
    extrapolate: 'clamp',
  });

  const likeOpacity = position.x.interpolate({
    inputRange: [0, SWIPE_THRESHOLD / 2],
    outputRange: [0, 1],
    extrapolate: 'clamp',
  });

  const nopeOpacity = position.x.interpolate({
    inputRange: [-SWIPE_THRESHOLD / 2, 0],
    outputRange: [1, 0],
    extrapolate: 'clamp',
  });

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => isTop,
      onMoveShouldSetPanResponder: () => isTop,
      onPanResponderMove: (_, gesture) => {
        position.setValue({ x: gesture.dx, y: gesture.dy });
      },
      onPanResponderRelease: (_, gesture) => {
        if (gesture.dx > SWIPE_THRESHOLD) {
          swipeOut('right');
        } else if (gesture.dx < -SWIPE_THRESHOLD) {
          swipeOut('left');
        } else {
          Animated.spring(position, {
            toValue: { x: 0, y: 0 },
            useNativeDriver: true,
          }).start();
        }
      },
    })
  ).current;

  const swipeOut = async (direction) => {
    await stopSound();
    const x = direction === 'right' ? SCREEN_W * 1.5 : -SCREEN_W * 1.5;
    Animated.timing(position, {
      toValue: { x, y: 0 },
      duration: 280,
      useNativeDriver: true,
    }).start(() => {
      if (direction === 'right') onSwipeRight(card);
      else onSwipeLeft(card);
    });
  };

  const scoreColor = card.score > 0.7 ? '#1DB954' : card.score > 0.4 ? '#F9A825' : '#888';
  const scorePercent = Math.round(card.score * 100);

  return (
    <Animated.View
      style={[
        styles.card,
        {
          transform: [
            { translateX: position.x },
            { translateY: position.y },
            { rotate },
          ],
          zIndex: isTop ? 10 : 5,
        },
      ]}
      {...panResponder.panHandlers}
    >
      {/* Carátula */}
      {imageLoading && (
        <View style={styles.imagePlaceholder}>
          <ActivityIndicator color="#1DB954" size="large" />
        </View>
      )}
      {card.image_url ? (
        <Image
          source={{ uri: card.image_url }}
          style={styles.image}
          onLoad={() => setImageLoading(false)}
          onError={() => setImageLoading(false)}
        />
      ) : (
        <View style={[styles.image, styles.noImage]}>
          <Text style={styles.noImageText}>🎵</Text>
        </View>
      )}

      {/* Gradiente inferior */}
      <LinearGradient
        colors={['transparent', 'rgba(0,0,0,0.85)']}
        style={styles.gradient}
      />

      {/* Info de la canción */}
      <View style={styles.info}>
        <Text style={styles.trackName} numberOfLines={2}>{card.name}</Text>
        <Text style={styles.artistName} numberOfLines={1}>{card.artists}</Text>

        <View style={styles.bottomRow}>
          {/* Score */}
          <View style={[styles.scoreBadge, { borderColor: scoreColor }]}>
            <Text style={[styles.scoreText, { color: scoreColor }]}>{scorePercent}%</Text>
          </View>

          {/* Botón play/pause */}
          {card.preview_url && (
            <TouchableOpacity style={styles.playBtn} onPress={togglePlay}>
              <Text style={styles.playIcon}>{playing ? '⏸' : '▶️'}</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* Indicadores LIKE / NOPE */}
      <Animated.View style={[styles.likeLabel, { opacity: likeOpacity }]}>
        <Text style={styles.likeLabelText}>✓ DALE</Text>
      </Animated.View>
      <Animated.View style={[styles.nopeLabel, { opacity: nopeOpacity }]}>
        <Text style={styles.nopeLabelText}>✗ PASO</Text>
      </Animated.View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: {
    position: 'absolute',
    width: CARD_W,
    height: CARD_H,
    borderRadius: 20,
    overflow: 'hidden',
    backgroundColor: '#1a1a2e',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.5,
    shadowRadius: 12,
    elevation: 10,
  },
  image: {
    width: '100%',
    height: '100%',
    resizeMode: 'cover',
  },
  imagePlaceholder: {
    position: 'absolute',
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#1a1a2e',
    zIndex: 1,
  },
  noImage: {
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#16213e',
  },
  noImageText: {
    fontSize: 80,
  },
  gradient: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: CARD_H * 0.55,
  },
  info: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    padding: 20,
  },
  trackName: {
    color: '#fff',
    fontSize: 22,
    fontWeight: '800',
    letterSpacing: -0.5,
    marginBottom: 4,
    textShadowColor: 'rgba(0,0,0,0.8)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  artistName: {
    color: 'rgba(255,255,255,0.75)',
    fontSize: 15,
    fontWeight: '500',
    marginBottom: 14,
  },
  bottomRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  scoreBadge: {
    borderWidth: 2,
    borderRadius: 20,
    paddingHorizontal: 12,
    paddingVertical: 4,
  },
  scoreText: {
    fontSize: 13,
    fontWeight: '700',
  },
  playBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(29,185,84,0.25)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: '#1DB954',
  },
  playIcon: {
    fontSize: 18,
  },
  likeLabel: {
    position: 'absolute',
    top: 40,
    left: 20,
    borderWidth: 4,
    borderColor: '#1DB954',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 6,
    transform: [{ rotate: '-15deg' }],
  },
  likeLabelText: {
    color: '#1DB954',
    fontSize: 22,
    fontWeight: '900',
  },
  nopeLabel: {
    position: 'absolute',
    top: 40,
    right: 20,
    borderWidth: 4,
    borderColor: '#FF4458',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 6,
    transform: [{ rotate: '15deg' }],
  },
  nopeLabelText: {
    color: '#FF4458',
    fontSize: 22,
    fontWeight: '900',
  },
});
