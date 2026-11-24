import { useCallback, useRef, useState } from "react";
import { sendChatMessage } from "../services/api.js";

function createWelcomeMessage() {
  return {
    id: "welcome",
    role: "assistant",
    time: new Date(),
    text: "Welcome. Tell me what your team needs, and I can help find approved vendors, check procurement policy, and prepare a purchase order for review.",
  };
}

export default function useProcurementChat() {
  const [threadId, setThreadId] = useState("");
  const [messages, setMessages] = useState(() => [createWelcomeMessage()]);
  const [prompt, setPrompt] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const sendingRef = useRef(false);
  const messageSequence = useRef(0);

  const nextMessageId = useCallback((role) => {
    messageSequence.current += 1;
    return `${role}-${Date.now()}-${messageSequence.current}`;
  }, []);

  const sendMessage = useCallback(
    async (value) => {
      const message = typeof value === "string" ? value.trim() : "";
      if (!message || sendingRef.current) return;

      sendingRef.current = true;
      setError("");
      setPrompt("");
      const userMessage = {
        id: nextMessageId("user"),
        role: "user",
        text: message,
        time: new Date(),
      };
      setMessages((current) => [...current, userMessage]);
      setIsSending(true);

      try {
        const result = await sendChatMessage({
          message,
          threadId: threadId || undefined,
        });
        setThreadId(result.thread_id);
        const assistantMessage = {
          id: nextMessageId("assistant"),
          role: "assistant",
          time: new Date(),
          text:
            result.response ||
            (result.status === "waiting_for_approval"
              ? "This request is paused for manager approval."
              : "The workflow completed. Review the purchase details below."),
          status: result.status,
          citations: result.citations,
          purchaseOrder: result.purchase_order,
        };
        setMessages((current) => [...current, assistantMessage]);
      } catch (sendError) {
        setError(
          sendError instanceof Error
            ? sendError.message
            : "Unable to send the request. Check the backend connection and try again.",
        );
      } finally {
        sendingRef.current = false;
        setIsSending(false);
      }
    },
    [nextMessageId, threadId],
  );

  const startNewConversation = useCallback(() => {
    if (sendingRef.current) return;
    setThreadId("");
    setMessages([createWelcomeMessage()]);
    setPrompt("");
    setError("");
  }, []);

  return {
    threadId,
    messages,
    prompt,
    setPrompt,
    isSending,
    error,
    sendMessage,
    startNewConversation,
  };
}