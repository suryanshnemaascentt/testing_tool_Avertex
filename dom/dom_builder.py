from __future__ import annotations


async def extract_live_dom(page):
    try:
        await page.wait_for_load_state("networkidle", timeout=7000)
    except Exception:
        pass

    # Scroll to trigger lazy-rendered form fields
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(600)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(300)
    except Exception:
        pass

    for attempt in range(3):
        try:
            elements = await page.evaluate("""
            () => {
                const selector = [
                    "button",
                    "a",
                    "input",
                    "select",
                    "textarea",
                    "label",
                    "[role='button']",
                    "[role='link']",
                    "[role='option']",
                    "[role='combobox']",
                    "[role='listbox']",
                    "[role='menuitem']",
                    "[role='menu']",
                    "[role='dialog']",
                    "[role='alertdialog']",
                    "[role='status']",
                    "[role='row']",
                    "[role='cell']",
                    "[role='gridcell']",
                    "td",
                    "th",
                    "span[data-id]",
                    "li[role='option']",
                    "li[role='menuitem']"
                ].join(", ");

                const nodes   = document.querySelectorAll(selector);
                const results = [];
                const seen    = new Set();

                for (let i = 0; i < nodes.length && results.length < 400; i++) {
                    const el = nodes[i];

                    if (
                        el.disabled ||
                        el.getAttribute("aria-hidden") === "true" ||
                        el.getAttribute("aria-disabled") === "true"
                    ) continue;

                    const style = window.getComputedStyle(el);
                    if (style.display === "none" || style.visibility === "hidden") continue;

                    const tag         = el.tagName.toLowerCase();
                    const elId        = el.id || "";
                    const roleAttr    = el.getAttribute("role") || "";
                    const type        = el.getAttribute("type") || "";
                    const value       = el.value || el.getAttribute("value") || el.defaultValue || "";
                    const placeholder = el.getAttribute("placeholder") || "";
                    const nameAttr    = el.getAttribute("name") || "";
                    const ariaLabel   = el.getAttribute("aria-label") || "";
                    const text        = (el.innerText || "").trim().slice(0, 200);
                    const dataId      = el.getAttribute("data-id") || "";
                    const dataTestId  = el.getAttribute("data-testid") || "";
                    const className   = el.className || "";

                    // Associated <label> text (floating labels support)
                    let associatedLabel = "";
                    if (el.labels && el.labels.length > 0) {
                        associatedLabel = (el.labels[0].innerText || "").trim();
                    }
                    const labelledBy = el.getAttribute("aria-labelledby");
                    if (!associatedLabel && labelledBy) {
                        const labelEl = document.getElementById(labelledBy);
                        if (labelEl) associatedLabel = (labelEl.innerText || "").trim();
                    }
                    if (!associatedLabel) {
                        const parentLabel = el.closest("label");
                        if (parentLabel) {
                            const clone = parentLabel.cloneNode(true);
                            const inputs = clone.querySelectorAll("input, select, textarea");
                            inputs.forEach(i => i.remove());
                            associatedLabel = (clone.innerText || "").trim();
                        }
                    }
                    if (!associatedLabel) {
                        const wrapper = el.closest(".MuiFormControl-root, .form-group, .field-wrapper, [class*='FormControl']");
                        if (wrapper) {
                            const legendOrLabel = wrapper.querySelector("label, legend, .MuiFormLabel-root, [class*='label']");
                            if (legendOrLabel) {
                                associatedLabel = (legendOrLabel.innerText || "").trim();
                            }
                        }
                    }

                    const label =
                        associatedLabel ||
                        ariaLabel       ||
                        placeholder     ||
                        nameAttr        ||
                        text            ||
                        roleAttr        ||
                        value           ||
                        "";

                    let selectorPath = "";
                    if (dataTestId) {
                        selectorPath = `[data-testid='${dataTestId}']`;
                    } else if (elId) {
                        selectorPath = "#" + CSS.escape(elId);
                    } else if (ariaLabel) {
                        selectorPath = `${tag}[aria-label='${CSS.escape(ariaLabel)}']`;
                    } else if (nameAttr) {
                        selectorPath = `${tag}[name='${CSS.escape(nameAttr)}']`;
                    } else if (text && text.length < 60) {
                        const safeText = text.replace(/'/g, "\\'");
                        selectorPath = `${tag}:has-text('${safeText}')`;
                    } else if (roleAttr) {
                        selectorPath = `${tag}[role='${roleAttr}']`;
                    } else {
                        selectorPath = tag;
                    }

                    if (seen.has(selectorPath)) continue;
                    seen.add(selectorPath);

                    results.push({
                        tag,
                        id:          elId,
                        type,
                        label,
                        text,
                        selector:    selectorPath,
                        value,
                        dataId,
                        dataTestId,
                        name:        nameAttr,
                        role:        roleAttr,
                        class:       className,
                        placeholder,
                        ariaLabel
                    });
                }

                return results;
            }
            """)

            print(f"[DOM] Extracted {len(elements)} elements")
            return elements

        except Exception as e:
            print(f"[WARN] DOM extraction failed (attempt {attempt + 1}): {e}")
            try:
                await page.wait_for_load_state("load", timeout=5000)
            except Exception:
                pass

    print("[ERR] DOM extraction failed after 3 attempts.")
    return []