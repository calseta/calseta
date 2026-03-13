import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/lib/auth";
import { LoginPage } from "@/pages/login";
import { router } from "./router";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function AuthGate() {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <LoginPage />;
  return <RouterProvider router={router} />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthGate />
        <Toaster
          theme="dark"
          position="bottom-right"
          toastOptions={{
            style: {
              background: "#0d1117",
              border: "1px solid #57635F",
              color: "#CCD0CF",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "13px",
            },
          }}
        />
      </AuthProvider>
    </QueryClientProvider>
  );
}
