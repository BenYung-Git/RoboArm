import { createCadStaticViewer } from "/static/js/virtual_demo_cad_3d.js?v=att_preview1";

/**
 * Inventory attachment preview host.
 * Cleans prior viewers/object URLs/raf before mounting a new type.
 */
export function createAttachmentPreviewController(host) {
  let disposed = false;
  let requestSeq = 0;
  let cadViewer = null;
  let objectUrl = null;
  let abortCtrl = null;

  function clearObjectUrl() {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
  }

  function clearCad() {
    if (cadViewer && typeof cadViewer.dispose === "function") {
      cadViewer.dispose();
    }
    cadViewer = null;
  }

  function clearHost() {
    if (abortCtrl) {
      abortCtrl.abort();
      abortCtrl = null;
    }
    clearCad();
    clearObjectUrl();
    host.innerHTML = "";
  }

  function setStatus(message, isError) {
    clearHost();
    const el = document.createElement("div");
    el.className = "tui-att-status" + (isError ? " is-error" : "");
    el.textContent = message || "";
    host.appendChild(el);
  }

  function addDownloadLink(url, label) {
    const a = document.createElement("a");
    a.className = "tui-btn tui-att-download";
    a.href = url;
    a.textContent = label || "Download";
    a.setAttribute("download", "");
    host.appendChild(a);
  }

  async function show(meta) {
    if (disposed) {
      return;
    }
    const seq = ++requestSeq;
    clearHost();
    if (!meta) {
      return;
    }
    const labels = meta.labels || {};
    if (meta.file_status && meta.file_status !== "ok") {
      setStatus(meta.message || labels.missing || "", true);
      if (meta.download_url) {
        addDownloadLink(meta.download_url, labels.download);
      }
      return;
    }
    if (!meta.preview_supported || meta.viewer === "download_only") {
      setStatus(meta.message || labels.unsupported || "", false);
      if (meta.download_url) {
        addDownloadLink(meta.download_url, labels.download);
      }
      return;
    }

    const loading = document.createElement("div");
    loading.className = "tui-att-status";
    loading.textContent = labels.loading || "";
    host.appendChild(loading);

    try {
      if (meta.viewer === "pdf" || meta.viewer === "image") {
        const frameWrap = document.createElement("div");
        frameWrap.className =
          meta.viewer === "pdf" ? "tui-att-pdf-wrap" : "tui-att-image-wrap";
        if (meta.viewer === "pdf") {
          const iframe = document.createElement("iframe");
          iframe.className = "tui-att-pdf";
          iframe.title = meta.File || "PDF";
          iframe.src = meta.content_url;
          frameWrap.appendChild(iframe);
        } else {
          const img = document.createElement("img");
          img.className = "tui-att-image";
          img.alt = meta.File || "";
          img.src = meta.content_url;
          frameWrap.appendChild(img);
        }
        if (seq !== requestSeq || disposed) {
          return;
        }
        host.innerHTML = "";
        host.appendChild(frameWrap);
        return;
      }

      if (meta.viewer === "glb") {
        if (seq !== requestSeq || disposed) {
          return;
        }
        host.innerHTML = "";
        const cadHost = document.createElement("div");
        cadHost.className = "tui-att-glb";
        host.appendChild(cadHost);
        const disclaimer = document.createElement("div");
        disclaimer.className = "tui-att-disclaimer";
        disclaimer.textContent =
          (meta.cad_static && meta.cad_static.disclaimer) ||
          labels.static_disclaimer ||
          "";
        host.appendChild(disclaimer);
        cadViewer = createCadStaticViewer(
          cadHost,
          meta.cad_static || { available: false, labels: labels }
        );
        return;
      }

      if (meta.viewer === "text") {
        abortCtrl = new AbortController();
        const response = await fetch(
          "/api/inventory/" +
            encodeURIComponent(meta.InventoryId) +
            "/attachments/" +
            encodeURIComponent(meta.TxId) +
            "/text",
          { signal: abortCtrl.signal }
        );
        if (seq !== requestSeq || disposed) {
          return;
        }
        if (!response.ok) {
          let detail = await response.text();
          try {
            const parsed = JSON.parse(detail);
            if (parsed && parsed.detail != null) {
              detail = String(parsed.detail);
            }
          } catch (_e) {
            // keep
          }
          setStatus(detail || labels.failed || "", true);
          return;
        }
        const data = await response.json();
        if (seq !== requestSeq || disposed) {
          return;
        }
        host.innerHTML = "";
        if (data.json_error) {
          const hint = document.createElement("div");
          hint.className = "tui-att-status is-warn";
          hint.textContent = data.json_error;
          host.appendChild(hint);
        }
        if (data.truncated && data.message) {
          const hint = document.createElement("div");
          hint.className = "tui-att-status is-warn";
          hint.textContent = data.message;
          host.appendChild(hint);
        }
        const pre = document.createElement("pre");
        pre.className = "tui-att-text";
        pre.textContent = data.text == null ? "" : String(data.text);
        host.appendChild(pre);
        return;
      }

      setStatus(labels.unsupported || "", false);
      if (meta.download_url) {
        addDownloadLink(meta.download_url, labels.download);
      }
    } catch (error) {
      if (error && error.name === "AbortError") {
        return;
      }
      if (seq !== requestSeq || disposed) {
        return;
      }
      setStatus(
        (labels.failed || "") +
          (error && error.message ? ": " + error.message : ""),
        true
      );
    }
  }

  function destroy() {
    disposed = true;
    requestSeq += 1;
    clearHost();
  }

  return {
    show: show,
    clear: clearHost,
    setStatus: setStatus,
    destroy: destroy,
  };
}

window.RoboArmAttachmentPreview = {
  create: createAttachmentPreviewController,
};
