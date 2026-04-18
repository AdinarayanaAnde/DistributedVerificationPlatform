import { useState } from "react";
import { api } from "../services/api";

export function useClientRegistration() {
  const [name, setName] = useState("");
  const [clientKey, setClientKey] = useState("");
  const [resourceName, setResourceName] = useState("default-resource");
  const [statusMessage, setStatusMessage] = useState("Ready");

  const registerClient = async () => {
    if (!name) {
      setStatusMessage("Enter a client name first");
      return;
    }
    try {
      const resp = await api.post("/clients/register", { name });
      setClientKey(resp.data.client_key);
      setStatusMessage("Client registered");
      return resp.data;
    } catch {
      setStatusMessage("Registration failed");
      throw new Error("Registration failed");
    }
  };

  return {
    name,
    setName,
    clientKey,
    setClientKey,
    resourceName,
    setResourceName,
    statusMessage,
    setStatusMessage,
    registerClient,
  };
}
