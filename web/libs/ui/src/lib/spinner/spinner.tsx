import { useEffect, type CSSProperties } from "react";
import styles from "./spinner.module.scss";
import { cn } from "@humansignal/shad/utils";
// Reuse shared spinner asset (currently mapped to Lunor.png)
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - JS module exports untyped object with urls
import Running from "../../../../datamanager/src/assets/running";

export type SpinnerProps = {
  className?: string;
  style?: CSSProperties;
  size?: number;
  stopped?: boolean;
};

export const Spinner = ({ className, style, size = 40, stopped = false }: SpinnerProps) => {
  const fullClassName = cn(styles.spinner, className);

  // Inject keyframes once to animate image (scale + rotate)
  useEffect(() => {
    const styleId = "ls-lunor-spin-anim";
    if (!document.getElementById(styleId)) {
      const styleEl = document.createElement("style");
      styleEl.id = styleId;
      styleEl.textContent = `@keyframes ls-lunor-spin {\n  0% { transform: scale(1) rotate(0deg); }\n  50% { transform: scale(1.2) rotate(180deg); }\n  100% { transform: scale(1) rotate(360deg); }\n}`;
      document.head.appendChild(styleEl);
    }
  }, []);

  const sizeWithUnit = typeof size === "number" ? `${size}px` : size;

  const imgStyles: CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: "contain",
    animation: stopped ? undefined : "ls-lunor-spin 2s ease-in-out infinite",
  };

  const source = Running.full;

  const containerStyle = { ...(style ?? {}) } as CSSProperties & Record<string, unknown>;
  // Define CSS variable for size in a TS-safe way
  (containerStyle as Record<string, unknown>)["--spinner-size"] = sizeWithUnit as unknown as string;

  return (
    <div className={fullClassName} style={containerStyle}>
      <img src={source.x1} srcSet={`${source.x1} 1x, ${source.x2} 2x`} style={imgStyles} alt="loading" />
    </div>
  );
};
