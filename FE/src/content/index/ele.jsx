import { useEffect, useMemo, useState } from "react";
import { marked } from "marked";

const markdownSources = import.meta.glob("./*.md", {
    eager: true,
    query: "?raw",
    import: "default",
});

function normalizePath(path) {
    return String(path || "").trim().replaceAll("\\", "/").toLowerCase();
}

function resolveMarkdownByPath(mdPath) {
    const normalizedPath = normalizePath(mdPath);
    if (!normalizedPath) {
        return "";
    }

    const direct = markdownSources[mdPath] || markdownSources[normalizedPath];
    if (typeof direct === "string") {
        return direct;
    }

    const matchedKey = Object.keys(markdownSources).find((key) => {
        const normalizedKey = normalizePath(key);
        return (
            normalizedKey === normalizedPath ||
            normalizedPath.endsWith(normalizedKey.replace(/^\.\//, "")) ||
            normalizedPath.endsWith(normalizedKey)
        );
    });

    if (!matchedKey) {
        return "";
    }

    const content = markdownSources[matchedKey];
    return typeof content === "string" ? content : "";
}

export function H({ width = "100%", children }) {
    const normalizedWidth =
        typeof width === "number" ? `${width}%` : width || "100%";

    return (
        <span
            style={{
                display: "inline-block",
                width: normalizedWidth,
                fontWeight: "bold",
            }}
        >
            {children}
        </span>
    );
}

export function TypingTitle({
    text = "HI，这是 灵·诊",
    fontSize = "clamp(2rem, 12vw, 7.5rem)",
    duration = 2.8,
    loop = false,
}) {
    const content = String(text ?? "");
    const chars = useMemo(() => Array.from(content), [content]);
    const total = Math.max(chars.length, 1);
    const stepMs = Math.max((duration * 1000) / total, 16);

    const [visibleCount, setVisibleCount] = useState(0);
    const [showCaret, setShowCaret] = useState(true);

    useEffect(() => {
        let intervalId;
        let timeoutId;

        setVisibleCount(0);
        setShowCaret(true);

        intervalId = window.setInterval(() => {
            setVisibleCount((previous) => {
                if (previous >= total) {
                    return previous;
                }
                return previous + 1;
            });
        }, stepMs);

        const finishMs = stepMs * total;

        if (loop) {
            timeoutId = window.setTimeout(() => {
                window.clearInterval(intervalId);
                setVisibleCount(0);
                setShowCaret(true);
            }, finishMs + 1000);
        } else {
            timeoutId = window.setTimeout(() => {
                window.clearInterval(intervalId);
                setShowCaret(false);
            }, finishMs + 1000);
        }

        return () => {
            if (intervalId) {
                window.clearInterval(intervalId);
            }
            if (timeoutId) {
                window.clearTimeout(timeoutId);
            }
        };
    }, [content, loop, stepMs, total]);

    const visibleText = chars.slice(0, visibleCount).join("");

    return (
        <span
            style={{
                display: "inline-flex",
                alignItems: "center",
                fontSize,
                fontWeight: "700",
                maxWidth: "100%",
                whiteSpace: "normal",
                overflowWrap: "anywhere",
            }}
            aria-label={content}
        >
            <span>{visibleText}</span>
            {showCaret ? (
                <span
                    style={{
                        display: "inline-block",
                        width: "0.08em",
                        height: "1em",
                        marginLeft: "0.06em",
                        backgroundColor: "currentColor",
                        animation: "typingCaretBlink 0.75s step-end infinite",
                    }}
                />
            ) : null}
            <style>{`
                @keyframes typingCaretBlink {
                    from, to { opacity: 1; }
                    50% { opacity: 0; }
                }
            `}</style>
        </span>
    );
}

export function ShuffleStackGallery({
    items = [],
    intervalMs = 3200,
    size = "md",
    cardWidth,
    sideReveal = "1.1rem",
    cardRadius = "0.9rem",
    mdBoxWidth = "100%",
    mdBoxHeight = "14rem",
}) {
    const safeItems = Array.isArray(items) ? items : [];
    const count = safeItems.length;
    const initialOrder = useMemo(
        () => safeItems.map((_, index) => index),
        [safeItems],
    );
    const [order, setOrder] = useState(initialOrder);
    const [hoveredIndex, setHoveredIndex] = useState(-1);
    const [isReadingMd, setIsReadingMd] = useState(false);

    const sizePresetWidth =
        size === "sm"
            ? "min(72vw, 18rem)"
            : size === "lg"
                ? "min(94vw, 30rem)"
                : "min(82vw, 22rem)";
    const effectiveCardWidth = cardWidth || sizePresetWidth;
    const effectiveIntervalMs = Math.max(intervalMs, 600);
    const transitionMs = Math.min(
        Math.max(Math.round(effectiveIntervalMs * 0.78), 800),
        2600,
    );
    const shouldPauseAutoplay = hoveredIndex >= 0 || isReadingMd;

    useEffect(() => {
        setOrder(initialOrder);
    }, [initialOrder]);

    useEffect(() => {
        if (count <= 1) {
            return;
        }

        if (shouldPauseAutoplay) {
            return;
        }

        const timer = window.setInterval(() => {
            setOrder((previous) => {
                if (previous.length <= 1) {
                    return previous;
                }
                return [...previous.slice(1), previous[0]];
            });
        }, effectiveIntervalMs);

        return () => window.clearInterval(timer);
    }, [count, effectiveIntervalMs, shouldPauseAutoplay]);

    const positionMap = useMemo(() => {
        const map = new Map();
        order.forEach((itemIndex, position) => {
            map.set(itemIndex, position);
        });
        return map;
    }, [order]);

    const topItemIndex = order[0] ?? 0;
    const activeItemIndex = hoveredIndex >= 0 ? hoveredIndex : topItemIndex;
    const activeItem = safeItems[activeItemIndex] || null;
    const topMarkdownRaw = resolveMarkdownByPath(activeItem?.mdPath);
    const topMarkdownHtml = useMemo(() => {
        if (!topMarkdownRaw) {
            return "";
        }
        return marked.parse(topMarkdownRaw);
    }, [topMarkdownRaw]);

    if (count === 0) {
        return null;
    }

    return (
        <div
            style={{
                width: `calc(${effectiveCardWidth} + ${sideReveal} * ${Math.max(count - 1, 0)})`,
                maxWidth: "100%",
                margin: "0 auto",
                display: "flex",
                flexDirection: "column",
                gap: "1rem",
            }}
        >
            <div
                style={{
                    display: "grid",
                    justifyContent: "start",
                }}
            >
                {safeItems.map((item, index) => {
                    const position = positionMap.get(index) ?? 0;
                    const isHovered = hoveredIndex === index;

                    return (
                        <a
                            key={`${item.src || "item"}-${index}`}
                            href={item.href || "#"}
                            aria-label={item.alt || `image-${index + 1}`}
                            onMouseEnter={() => setHoveredIndex(index)}
                            onMouseLeave={() => setHoveredIndex(-1)}
                            onFocus={() => setHoveredIndex(index)}
                            onBlur={() => setHoveredIndex(-1)}
                            style={{
                                gridArea: "1 / 1",
                                width: effectiveCardWidth,
                                maxWidth: "100%",
                                borderRadius: cardRadius,
                                overflow: "hidden",
                                boxShadow: isHovered
                                    ? "0 12px 24px rgba(0, 0, 0, 0.18)"
                                    : "0 6px 14px rgba(0, 0, 0, 0.12)",
                                zIndex: isHovered ? count + 10 : count - position,
                                transform: isHovered
                                    ? `translateX(calc(${sideReveal} * ${position})) translateY(-6px)`
                                    : `translateX(calc(${sideReveal} * ${position})) translateY(0)`,
                                willChange: "transform",
                                transition:
                                    `transform ${transitionMs}ms cubic-bezier(0.2, 0.85, 0.25, 1), box-shadow 360ms ease`,
                                background: "#fff",
                            }}
                        >
                            <img
                                src={item.src}
                                alt={item.alt || ""}
                                style={{
                                    width: "100%",
                                    height: "auto",
                                    display: "block",
                                }}
                            />
                        </a>
                    );
                })}
            </div>

            <div
                style={{
                    width: mdBoxWidth,
                    maxWidth: "100%",
                    height: mdBoxHeight,
                    padding: "0.9rem 1rem",
                    borderRadius: "0.8rem",
                    border: "1px solid rgba(128, 128, 128, 0.25)",
                    background: "rgba(255, 255, 255, 0.65)",
                    textAlign: "left",
                    lineHeight: "1.7",
                    overflowWrap: "anywhere",
                    overflowY: "auto",
                }}
                onMouseEnter={() => setIsReadingMd(true)}
                onMouseLeave={() => setIsReadingMd(false)}
                onFocus={() => setIsReadingMd(true)}
                onBlur={() => setIsReadingMd(false)}
                tabIndex={0}
            >
                {topMarkdownHtml ? (
                    <div dangerouslySetInnerHTML={{ __html: topMarkdownHtml }} />
                ) : (
                    <span>未配置此图片的说明文档。</span>
                )}
            </div>
        </div>
    );
}
