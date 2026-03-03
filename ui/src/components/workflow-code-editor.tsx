import { useCallback, useRef } from "react";
import CodeMirror, { type ReactCodeMirrorRef } from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { EditorView, keymap } from "@codemirror/view";
import { createTheme } from "@uiw/codemirror-themes";
import { tags as t } from "@lezer/highlight";

/**
 * Calseta dark theme for CodeMirror — matches the app's color palette exactly.
 *
 * Colors pulled from index.css :root variables:
 *   background: #080b0f, surface: #0d1117, surface-hover: #111820
 *   foreground: #CCD0CF, dim: #57635F, border: #1e2a25
 *   teal: #4D7D71, teal-light: #7FCAB8, amber: #FFBB1A, red: #EA591B
 */
const calsetaTheme = createTheme({
  theme: "dark",
  settings: {
    background: "#0d1117",
    foreground: "#CCD0CF",
    caret: "#7FCAB8",
    selection: "#4D7D7133",
    selectionMatch: "#4D7D7122",
    lineHighlight: "#111820",
    gutterBackground: "#0a0d12",
    gutterForeground: "#57635F",
    gutterBorder: "#1e2a25",
    fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
  },
  styles: [
    // Comments
    { tag: t.comment, color: "#57635F", fontStyle: "italic" },
    { tag: t.lineComment, color: "#57635F", fontStyle: "italic" },
    { tag: t.blockComment, color: "#57635F", fontStyle: "italic" },

    // Strings
    { tag: t.string, color: "#7FCAB8" },
    { tag: t.special(t.string), color: "#7FCAB8" },

    // Numbers and booleans
    { tag: t.number, color: "#FFBB1A" },
    { tag: t.bool, color: "#FFBB1A" },

    // Keywords (def, return, if, else, async, await, import, from, etc.)
    { tag: t.keyword, color: "#EA591B" },
    { tag: t.controlKeyword, color: "#EA591B" },

    // Function/method definitions and calls
    { tag: t.function(t.definition(t.variableName)), color: "#7FCAB8", fontWeight: "600" },
    { tag: t.function(t.variableName), color: "#CCD0CF" },

    // Class definitions
    { tag: t.definition(t.className), color: "#FFBB1A", fontWeight: "600" },
    { tag: t.className, color: "#FFBB1A" },

    // Variables and properties
    { tag: t.variableName, color: "#CCD0CF" },
    { tag: t.definition(t.variableName), color: "#CCD0CF" },
    { tag: t.propertyName, color: "#7FCAB8" },

    // Operators and punctuation
    { tag: t.operator, color: "#EA591B" },
    { tag: t.punctuation, color: "#57635F" },
    { tag: t.bracket, color: "#CCD0CF" },

    // Decorators (@)
    { tag: t.meta, color: "#4D7D71" },

    // Type annotations
    { tag: t.typeName, color: "#FFBB1A" },

    // Special: None, self
    { tag: t.null, color: "#FFBB1A" },
    { tag: t.self, color: "#EA591B", fontStyle: "italic" },

    // Built-in names
    { tag: t.standard(t.variableName), color: "#FFBB1A" },
  ],
});

/** Extra editor styles for matching Calseta's visual language. */
const editorBaseTheme = EditorView.theme({
  "&": {
    fontSize: "13px",
    borderRadius: "0.5rem",
    border: "1px solid #1e2a25",
  },
  "&.cm-focused": {
    outline: "1px solid #4D7D71",
    outlineOffset: "-1px",
  },
  ".cm-gutters": {
    borderRight: "1px solid #1e2a25",
    paddingRight: "4px",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "#111820",
    color: "#7FCAB8",
  },
  ".cm-matchingBracket": {
    backgroundColor: "#4D7D7140",
    outline: "1px solid #4D7D7160",
  },
  ".cm-selectionBackground": {
    backgroundColor: "#4D7D7133 !important",
  },
  ".cm-cursor": {
    borderLeftColor: "#7FCAB8",
    borderLeftWidth: "2px",
  },
  ".cm-content": {
    padding: "8px 0",
  },
  ".cm-line": {
    padding: "0 12px",
  },
  // Scrollbar styling
  ".cm-scroller::-webkit-scrollbar": {
    width: "6px",
    height: "6px",
  },
  ".cm-scroller::-webkit-scrollbar-track": {
    background: "transparent",
  },
  ".cm-scroller::-webkit-scrollbar-thumb": {
    background: "#1e2a25",
    borderRadius: "3px",
  },
  ".cm-scroller::-webkit-scrollbar-thumb:hover": {
    background: "#2a3530",
  },
});

interface WorkflowCodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  onSave?: () => void;
  height?: string;
  readOnly?: boolean;
}

export function WorkflowCodeEditor({
  value,
  onChange,
  onSave,
  height = "500px",
  readOnly = false,
}: WorkflowCodeEditorProps) {
  const editorRef = useRef<ReactCodeMirrorRef>(null);

  const saveKeymap = useCallback(() => {
    if (!onSave) return [];
    return [
      keymap.of([
        {
          key: "Mod-s",
          run: () => {
            onSave();
            return true;
          },
        },
      ]),
    ];
  }, [onSave]);

  return (
    <CodeMirror
      ref={editorRef}
      value={value}
      onChange={onChange}
      height={height}
      theme={calsetaTheme}
      readOnly={readOnly}
      basicSetup={{
        lineNumbers: true,
        highlightActiveLineGutter: true,
        highlightActiveLine: true,
        bracketMatching: true,
        closeBrackets: true,
        autocompletion: true,
        indentOnInput: true,
        foldGutter: true,
        tabSize: 4,
      }}
      extensions={[python(), editorBaseTheme, ...saveKeymap()]}
    />
  );
}
