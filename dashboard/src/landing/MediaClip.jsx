import { useEffect, useRef, useState } from "react";

/**
 * Autoplaying, looping, muted video clip for the landing page.
 *
 * Supports two orientations:
 *   - "portrait"  (9:16) → rendered as a tall product card with a soft frame
 *   - "landscape" (16:9) → rendered as a full-width band
 *
 * Resilient by design:
 *   - If the source file is missing or errors, we render `fallback` instead of
 *     a broken/black box (so the page never looks broken pre-asset).
 *   - Honors prefers-reduced-motion: shows the poster image, no autoplay.
 */
export default function MediaClip({
  src,
  poster,
  orientation = "portrait",
  className = "",
  fallback = null,
}) {
  const videoRef = useRef(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (reduce) {
      v.removeAttribute("autoplay");
      v.pause();
    }
  }, []);

  if (failed && fallback) return fallback;

  return (
    <div className={`mc mc-${orientation} ${className}`.trim()}>
      <video
        ref={videoRef}
        className="mc-video"
        src={src}
        poster={poster}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        onError={() => setFailed(true)}
      />
    </div>
  );
}
