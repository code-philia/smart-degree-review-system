export function startBreezeRenderer(layer: HTMLDivElement, art: HTMLDivElement, scene: HTMLDivElement) {
    let frame = 0;
    function sync() {
      frame = 0;
      const rect = scene.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) return;
      const parts = getComputedStyle(scene).backgroundPosition.split(/\s+/);
      const px = parseFloat(parts[0]) / 100;
      const py = parseFloat(parts[1] || parts[0]) / 100;
      const x = Number.isFinite(px) ? px : 0.5;
      const y = Number.isFinite(py) ? py : 0.5;
      const scale = Math.max(rect.width / 1672, rect.height / 940.5);
      const left = rect.left + (rect.width - 1672 * scale) * x;
      const top = rect.top + (rect.height - 940.5 * scale) * y;
      art.style.transform = "translate(" + left + "px," + top + "px) scale(" + scale + ")";
      layer.dataset.ready = "true";
    }
    function schedule() {
      if (!frame && !document.hidden) frame = requestAnimationFrame(sync);
    }
    function visibility() {
      layer.dataset.active = String(!document.hidden);
      if (document.hidden) {
        cancelAnimationFrame(frame);
        frame = 0;
      } else schedule();
    }
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(schedule) : null;
    if (observer) observer.observe(scene);
    window.addEventListener("resize", schedule);
    document.addEventListener("visibilitychange", visibility);
    sync();
    visibility();
    return () => {
      cancelAnimationFrame(frame);
      if (observer) observer.disconnect();
      window.removeEventListener("resize", schedule);
      document.removeEventListener("visibilitychange", visibility);
      layer.dataset.active = "false";
      frame = 0;
    };

}
