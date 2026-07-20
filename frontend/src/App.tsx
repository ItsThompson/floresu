import { Button } from "@/components/ui/button";

function App() {
  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-4">
      <h1 className="text-3xl font-semibold tracking-tight">Floresu</h1>
      <p className="text-muted-foreground">Premium career tracker.</p>
      <Button>Get started</Button>
    </main>
  );
}

export default App;
