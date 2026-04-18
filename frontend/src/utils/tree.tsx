import type { TestItem, TreeNode, TestStatus } from "../types";

export function buildTree(tests: TestItem[]): TreeNode[] {
  const root: TreeNode = { name: "root", path: "", type: "folder", children: [] };
  for (const test of tests) {
    const [filePath, funcName] = test.nodeid.split("::");
    const pathParts = filePath.split("/");
    let current = root;
    for (let i = 0; i < pathParts.length - 1; i++) {
      const folderPath = pathParts.slice(0, i + 1).join("/");
      let folder = current.children.find(
        (c) => c.path === folderPath && c.type === "folder"
      );
      if (!folder) {
        folder = { name: pathParts[i], path: folderPath, type: "folder", children: [] };
        current.children.push(folder);
      }
      current = folder;
    }
    let fileNode = current.children.find(
      (c) => c.path === filePath && c.type === "file"
    );
    if (!fileNode) {
      fileNode = { name: pathParts[pathParts.length - 1], path: filePath, type: "file", children: [] };
      current.children.push(fileNode);
    }
    fileNode.children.push({
      name: funcName,
      path: test.nodeid,
      type: "test",
      nodeid: test.nodeid,
      children: [],
    });
  }
  return root.children;
}

export function getAllTestIds(node: TreeNode): string[] {
  if (node.type === "test" && node.nodeid) return [node.nodeid];
  return node.children.flatMap(getAllTestIds);
}

export function getCheckState(node: TreeNode, selected: string[]): "none" | "some" | "all" {
  const ids = getAllTestIds(node);
  if (ids.length === 0) return "none";
  const selCount = ids.filter((id) => selected.includes(id)).length;
  if (selCount === 0) return "none";
  if (selCount === ids.length) return "all";
  return "some";
}

export function getAggregateStatus(statuses: TestStatus[]): TestStatus {
  if (statuses.length === 0) return "not-started";
  if (statuses.some((s) => s === "error")) return "error";
  if (statuses.some((s) => s === "fail")) return "fail";
  if (statuses.some((s) => s === "running")) return "running";
  if (statuses.every((s) => s === "done")) return "done";
  return "not-started";
}

export function getNodeStatus(
  node: TreeNode,
  statuses: Record<string, TestStatus>,
  selected: string[]
): TestStatus | null {
  const ids = getAllTestIds(node).filter((id) => selected.includes(id));
  if (ids.length === 0) return null;
  const childStatuses = ids.map((id) => statuses[id] || "not-started");
  return getAggregateStatus(childStatuses);
}
