import { render, screen } from "@testing-library/react";
import App from "./App";

describe("App", () => {
  it("renders the phase 1 placeholder shell", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "StockTradeBot" })).toBeInTheDocument();
    expect(screen.getByText(/FastAPI runtime skeleton/)).toBeInTheDocument();
    expect(screen.getByText(/Later phases will replace this placeholder/)).toBeInTheDocument();
  });
});
