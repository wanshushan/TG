import { useEffect, useMemo, useState } from "react";
import { marked } from "marked";

const markdownSources = import.meta.glob("./*.md", {
    eager: true,
    query: "?raw",
    import: "default",
});

const imageSources = import.meta.glob("./*.png", {
    eager: true,
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

function resolveImageByPath(imagePath) {
    const original = String(imagePath || "").trim();
    const normalizedPath = normalizePath(original);
    if (!normalizedPath) {
        return "";
    }

    const direct = imageSources[original] || imageSources[normalizedPath];
    if (typeof direct === "string") {
        return direct;
    }

    const matchedKey = Object.keys(imageSources).find((key) => {
        const normalizedKey = normalizePath(key);
        const normalizedKeyWithoutDot = normalizedKey.replace(/^\.\//, "");
        return (
            normalizedKey === normalizedPath ||
            normalizedPath.endsWith(normalizedKey) ||
            normalizedPath.endsWith(normalizedKeyWithoutDot)
        );
    });

    if (!matchedKey) {
        return original;
    }

    const content = imageSources[matchedKey];
    return typeof content === "string" ? content : original;
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

function splitTextByMode(text, splitBy) {
    const value = String(text ?? "");

    if (splitBy === "words") {
        const words = value.match(/\S+\s*/g);
        return words && words.length > 0 ? words : [value];
    }

    if (splitBy === "lines") {
        const lines = value.split(/\r?\n/);
        return lines.length > 0 ? lines : [value];
    }

    return Array.from(value);
}

function getStaggerDelay(index, length, staggerDuration, staggerFrom) {
    const safeIndex = Math.max(index, 0);
    const safeLength = Math.max(length, 1);
    const base = Math.max(staggerDuration, 0);

    if (staggerFrom === "last") {
        return (safeLength - safeIndex - 1) * base;
    }

    if (staggerFrom === "center") {
        const center = (safeLength - 1) / 2;
        return Math.abs(safeIndex - center) * base;
    }

    return safeIndex * base;
}

export function RotatingText({
    texts = [],
    rotationInterval = 2000,
    loop = true,
    auto = true,
    splitBy = "characters",
    onNext,
    mainClassName = "",
    splitLevelClassName = "",
    elementLevelClassName = "",
    staggerDuration = 0.03,
    staggerFrom = "first",
    transition = { duration: 0.42, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
}) {
    const safeTexts = Array.isArray(texts) ? texts.filter((item) => item !== null && item !== undefined) : [];
    const [activeIndex, setActiveIndex] = useState(0);

    useEffect(() => {
        if (!auto || safeTexts.length <= 1) {
            return;
        }

        const intervalMs = Math.max(rotationInterval, 500);
        const timer = window.setInterval(() => {
            setActiveIndex((previous) => {
                const next = previous + 1;
                if (next >= safeTexts.length) {
                    if (!loop) {
                        return previous;
                    }
                    onNext?.(0);
                    return 0;
                }
                onNext?.(next);
                return next;
            });
        }, intervalMs);

        return () => window.clearInterval(timer);
    }, [auto, loop, onNext, rotationInterval, safeTexts.length]);

    useEffect(() => {
        if (activeIndex <= safeTexts.length - 1) {
            return;
        }
        setActiveIndex(0);
    }, [activeIndex, safeTexts.length]);

    if (safeTexts.length === 0) {
        return null;
    }

    const currentText = String(safeTexts[activeIndex] ?? "");
    const units = splitTextByMode(currentText, splitBy);
    const animationDuration = Math.max(Number(transition?.duration) || 0.42, 0.1);
    const animationEasing = String(transition?.easing || "cubic-bezier(0.22, 1, 0.36, 1)");

    return (
        <span
            className={mainClassName}
            style={{
                display: "inline-flex",
                alignItems: "baseline",
                overflow: "hidden",
                verticalAlign: "baseline",
                minHeight: "1em",
            }}
            aria-live="polite"
        >
            <span
                key={`${activeIndex}-${currentText}`}
                className={splitLevelClassName}
                style={{
                    display: "inline-flex",
                    alignItems: "baseline",
                    whiteSpace: splitBy === "lines" ? "pre-line" : "pre-wrap",
                }}
            >
                {units.map((part, index) => {
                    const delay = getStaggerDelay(index, units.length, staggerDuration, staggerFrom);
                    const displayText = splitBy === "characters" && part === " " ? "\u00A0" : part;

                    return (
                        <span
                            key={`${part}-${index}`}
                            className={elementLevelClassName}
                            style={{
                                display: "inline-block",
                                opacity: 0,
                                transform: "translateY(110%)",
                                animationName: "rbRotateItemIn",
                                animationDuration: `${animationDuration}s`,
                                animationTimingFunction: animationEasing,
                                animationFillMode: "forwards",
                                animationDelay: `${delay}s`,
                            }}
                        >
                            {displayText}
                        </span>
                    );
                })}
            </span>

            <style>{`
                @keyframes rbRotateItemIn {
                    0% {
                        opacity: 0;
                        transform: translateY(110%);
                    }
                    100% {
                        opacity: 1;
                        transform: translateY(0);
                    }
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
                    const defaultImageSrc = resolveImageByPath(item.src);
                    const mobileImageSrc = resolveImageByPath(item.srcMobile);

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
                            {mobileImageSrc ? (
                                <picture>
                                    <source
                                        media="(max-width: 768px)"
                                        srcSet={mobileImageSrc}
                                    />
                                    <img
                                        src={defaultImageSrc}
                                        alt={item.alt || ""}
                                        style={{
                                            width: "100%",
                                            height: "auto",
                                            display: "block",
                                        }}
                                    />
                                </picture>
                            ) : (
                                <img
                                    src={defaultImageSrc}
                                    alt={item.alt || ""}
                                    style={{
                                        width: "100%",
                                        height: "auto",
                                        display: "block",
                                    }}
                                />
                            )}
                        </a>
                    );
                })}
            </div>

            <div
                style={{
                    width: mdBoxWidth,
                    maxWidth: "100%",
                    height: mdBoxHeight,
                    padding: "1rem 1.1rem",
                    borderRadius: cardRadius,
                    border: "1px solid rgba(0, 0, 0, 0.06)",
                    boxShadow: "0 6px 14px rgba(0, 0, 0, 0.12)",
                    background: "#fff",
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
