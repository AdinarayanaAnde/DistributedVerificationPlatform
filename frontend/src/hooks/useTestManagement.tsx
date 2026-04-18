import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../services/api";
import type { TestItem, TreeNode, TestSuite } from "../types";
import { getAllTestIds } from "../utils/tree";

export function useTestManagement(clientKey?: string) {
  const [tests, setTests] = useState<TestItem[]>([]);
  const [selectedTests, setSelectedTests] = useState<string[]>([]);
  const [testFilter, setTestFilter] = useState("");
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [testSuites, setTestSuites] = useState<TestSuite[]>([]);
  const [selectedSuiteIds, setSelectedSuiteIds] = useState<string[]>([]);
  const [isLoadingTests, setIsLoadingTests] = useState(true);
  const [testDiscoveryError, setTestDiscoveryError] = useState<string | null>(null);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCount = useRef(0);

  const refreshTests = useCallback(async () => {
    setIsLoadingTests(true);
    setTestDiscoveryError(null);
    try {
      const params: Record<string, string> = {};
      if (clientKey) params.client_key = clientKey;
      const resp = await api.get<TestItem[]>("/tests/discover", { params });
      setTests(resp.data);
      retryCount.current = 0; // Reset on success

      // Prune selectedTests: remove nodeids that no longer exist in discovered tests
      const validIds = new Set(resp.data.map((t) => t.nodeid));
      setSelectedTests((prev) => {
        const pruned = prev.filter((id) => validIds.has(id));
        return pruned.length === prev.length ? prev : pruned;
      });

      // Start collapsed — expand only the top-level root folder
      const paths = new Set<string>();
      resp.data.forEach((t) => {
        const parts = t.nodeid.split("/");
        if (parts.length > 0) paths.add(parts[0]);
      });
      setExpandedNodes(paths);
    } catch (e) {
      console.error("Failed to load tests", e);
      const isNetworkError = e instanceof Error && e.message.includes("Network Error");
      setTestDiscoveryError(
        isNetworkError
          ? "Unable to reach server. Make sure the backend is running."
          : "Failed to discover tests. Please try again."
      );
      // Auto-retry on network errors with capped backoff (3s, 6s, 10s, 10s, ...)
      if (isNetworkError) {
        const delay = Math.min(3000 * Math.pow(2, retryCount.current), 10000);
        retryCount.current += 1;
        retryTimer.current = setTimeout(() => {
          refreshTests();
        }, delay);
      }
    } finally {
      setIsLoadingTests(false);
    }
  }, [clientKey]);

  // Load tests on mount and when clientKey changes
  useEffect(() => {
    refreshTests();
    return () => {
      if (retryTimer.current) clearTimeout(retryTimer.current);
    };
  }, [refreshTests]);

  const refreshSuites = useCallback(async () => {
    try {
      const resp = await api.get<TestSuite[]>("/test-suites");
      setTestSuites(resp.data);
    } catch (e) {
      console.error("Failed to load test suites", e);
    }
  }, []);

  // Load test suites on mount
  useEffect(() => {
    refreshSuites();
  }, [refreshSuites]);

  const toggleExpanded = (path: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const toggleNodeSelection = (node: TreeNode) => {
    const ids = getAllTestIds(node);
    const allSelected = ids.length > 0 && ids.every((id) => selectedTests.includes(id));
    if (allSelected) setSelectedTests((prev) => prev.filter((id) => !ids.includes(id)));
    else setSelectedTests((prev) => [...new Set([...prev, ...ids])]);
  };

  // Multi-suite toggle: select/deselect suites, union their tests
  const toggleSuite = useCallback((suite: TestSuite) => {
    setSelectedSuiteIds((prev) => {
      const isSelected = prev.includes(suite.id);
      const next = isSelected ? prev.filter((id) => id !== suite.id) : [...prev, suite.id];
      // Recompute selected tests from all selected suites
      const allSuiteTests = new Set<string>();
      const suitesById = new Map(testSuites.map((s) => [s.id, s]));
      for (const sid of next) {
        const s = suitesById.get(sid);
        if (s) s.tests.forEach((t) => allSuiteTests.add(t));
      }
      setSelectedTests([...allSuiteTests]);
      return next;
    });
  }, [testSuites]);

  const createCustomSuite = useCallback(async (name: string, description: string, tests: string[], tags: string[]) => {
    try {
      await api.post("/custom-suites", { name, description, tests, tags });
      await refreshSuites();
      return true;
    } catch (e) {
      console.error("Failed to create custom suite", e);
      return false;
    }
  }, [refreshSuites]);

  const deleteCustomSuite = useCallback(async (suiteId: string) => {
    // Extract numeric ID from "custom-123" format
    const numericId = suiteId.replace("custom-", "");
    try {
      await api.delete(`/custom-suites/${numericId}`);
      setSelectedSuiteIds((prev) => prev.filter((id) => id !== suiteId));
      await refreshSuites();
      return true;
    } catch (e) {
      console.error("Failed to delete custom suite", e);
      return false;
    }
  }, [refreshSuites]);

  return {
    tests,
    selectedTests,
    setSelectedTests,
    testFilter,
    setTestFilter,
    expandedNodes,
    toggleExpanded,
    toggleNodeSelection,
    testSuites,
    selectedSuiteIds,
    toggleSuite,
    createCustomSuite,
    deleteCustomSuite,
    refreshSuites,
    refreshTests,
    isLoadingTests,
    testDiscoveryError,
  };
}
