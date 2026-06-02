import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { Platform, StyleSheet, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import LoadingScreen from "./screens/LoadingScreen";
import SearchSeedScreen from "./screens/SearchSeedScreen";
import SwipeScreen from "./screens/SwipeScreen";
import PlaylistScreen from "./screens/PlaylistScreen";

const Stack = createNativeStackNavigator();

export default function App() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <View style={styles.shell}>
        <NavigationContainer>
          <StatusBar style="light" />
          <Stack.Navigator
            initialRouteName="Loading"
            screenOptions={{
              headerShown: false,
              animation: "slide_from_right",
              contentStyle: { backgroundColor: "#0a0a0a" },
            }}
          >
            <Stack.Screen name="Loading" component={LoadingScreen} />
            <Stack.Screen name="SearchSeed" component={SearchSeedScreen} />
            <Stack.Screen name="Swipe" component={SwipeScreen} />
            <Stack.Screen name="Playlist" component={PlaylistScreen} />
          </Stack.Navigator>
        </NavigationContainer>
      </View>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: "#050505",
  },
  shell: {
    flex: 1,
    width: "100%",
    minHeight: Platform.OS === "web" ? "100vh" : undefined,
    backgroundColor: "#0a0a0a",
  },
});
