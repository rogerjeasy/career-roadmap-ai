import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="bg-bg flex min-h-screen flex-col items-center justify-center gap-8 p-12">
      <h1 className="font-serif text-6xl font-light tracking-tight text-ink">
        Career Roadmap <em className="text-green italic">AI</em>
      </h1>
      <p className="text-ink-2 max-w-md text-center text-lg">
        Setup is working — fonts, palette, Tailwind v4, and shadcn/ui are wired up.
      </p>
      <div className="flex gap-3">
        <Button>Primary action</Button>
        <Button variant="outline">Secondary</Button>
      </div>
    </main>
  );
}