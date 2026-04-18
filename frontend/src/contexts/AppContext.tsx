import { createContext, useContext, ReactNode, useState, useCallback } from "react";
import type { ExplorerMode } from "../types";
import { useClientRegistration } from "../hooks/useClientRegistration";
import { useRunManagement } from "../hooks/useRunManagement";
import { useTestManagement } from "../hooks/useTestManagement";
import { useTheme } from "../hooks/useTheme";
import { useTabManagement } from "../hooks/useTabManagement";

export interface AppContextType {
  client: ReturnType<typeof useClientRegistration>;
  runMgmt: ReturnType<typeof useRunManagement>;
  testMgmt: ReturnType<typeof useTestManagement>;
  theme: ReturnType<typeof useTheme>;
  tabs: ReturnType<typeof useTabManagement>;
  sidebarWidth: number;
  setSidebarWidth: (width: number) => void;
  explorerMode: ExplorerMode;
  setExplorerMode: (mode: ExplorerMode) => void;
  cliCommand: string;
  setCliCommand: (command: string) => void;
  selectedSetupConfigId: number | null;
  setSelectedSetupConfigId: (id: number | null) => void;
  selectedTeardownConfigId: number | null;
  setSelectedTeardownConfigId: (id: number | null) => void;
  onResizeStart: (e: React.MouseEvent) => void;
}

export const AppContext = createContext<AppContextType | null>(null);

export function useAppContext() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error("useAppContext must be used within AppProvider");
  }
  return context;
}

export interface AppProviderProps {
  children: ReactNode;
}

export function AppProvider({ children }: AppProviderProps) {
  const client = useClientRegistration();
  const runMgmt = useRunManagement();
  const testMgmt = useTestManagement(client.clientKey);
  const theme = useTheme();
  const tabs = useTabManagement();

  const [sidebarWidth, setSidebarWidth] = useState(340);
  const [explorerMode, setExplorerMode] = useState<ExplorerMode>("tests");
  const [cliCommand, setCliCommand] = useState("");
  const [selectedSetupConfigId, setSelectedSetupConfigId] = useState<number | null>(null);
  const [selectedTeardownConfigId, setSelectedTeardownConfigId] = useState<number | null>(null);

  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = sidebarWidth;

      const onMouseMove = (ev: MouseEvent) => {
        const newWidth = Math.min(600, Math.max(220, startWidth + ev.clientX - startX));
        setSidebarWidth(newWidth);
      };
      const onMouseUp = () => {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    [sidebarWidth]
  );

  const value: AppContextType = {
    client,
    runMgmt,
    testMgmt,
    theme,
    tabs,
    sidebarWidth,
    setSidebarWidth,
    explorerMode,
    setExplorerMode,
    cliCommand,
    setCliCommand,
    selectedSetupConfigId,
    setSelectedSetupConfigId,
    selectedTeardownConfigId,
    setSelectedTeardownConfigId,
    onResizeStart: handleResizeStart,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
