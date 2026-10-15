import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, Home, RefreshCw } from "lucide-react";

function ErrorFallback({ title, message }: { title: string; message: string }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-6">
      <section className="w-full max-w-lg rounded-2xl border border-red/20 bg-surface p-8 text-center shadow-soft">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red/10 text-red">
          <AlertTriangle size={24} />
        </span>
        <h1 className="mt-4 text-xl font-semibold text-text">{title}</h1>
        <p className="mt-2 break-words text-sm leading-6 text-muted">{message}</p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="flex items-center gap-2 rounded-lg bg-blue px-4 py-2 text-sm font-medium text-white"
          >
            <RefreshCw size={15} />重新加载
          </button>
          <button
            type="button"
            onClick={() => window.location.assign("/workspace")}
            className="flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-2 text-sm font-medium text-text"
          >
            <Home size={15} />返回工作台
          </button>
        </div>
      </section>
    </main>
  );
}

export class AppErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("VideoX UI error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return <ErrorFallback title="页面运行出现错误" message={this.state.error.message || "未知界面错误"} />;
    }
    return this.props.children;
  }
}
