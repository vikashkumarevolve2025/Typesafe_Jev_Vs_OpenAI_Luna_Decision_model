"use client";

import type { CSSProperties } from "react";
import { Chessboard } from "react-chessboard";

type Props = {
  fen: string;
  lastMove?: { from: string; to: string } | null;
};

// Read-only board: the arena plays itself, so dragging is disabled.
// react-chessboard v5 takes all settings through a single `options` prop.
export default function Board({ fen, lastMove }: Props) {
  const squareStyles: Record<string, CSSProperties> = {};
  if (lastMove) {
    squareStyles[lastMove.from] = { background: "rgba(255, 214, 10, 0.45)" };
    squareStyles[lastMove.to] = { background: "rgba(255, 214, 10, 0.6)" };
  }

  return (
    <div className="board-frame">
      <Chessboard
        options={{
          id: "arena-board",
          position: fen,
          allowDragging: false,
          showNotation: true,
          animationDurationInMs: 250,
          darkSquareStyle: { backgroundColor: "#779556" },
          lightSquareStyle: { backgroundColor: "#ebecd0" },
          squareStyles,
        }}
      />
    </div>
  );
}
