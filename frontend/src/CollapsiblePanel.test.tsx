import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CollapsiblePanel from "./components/CollapsiblePanel";

const panel = (name: string) =>
  screen.getByRole("button", { name }).closest("details")!;
test("panels have configurable independent defaults and accessible controls", async () => {
  render(
    <>
      <CollapsiblePanel title="Current work" defaultOpen>
        <p>Current content</p>
      </CollapsiblePanel>
      <CollapsiblePanel title="History" summary="2 entries">
        <p>Old content</p>
      </CollapsiblePanel>
    </>,
  );
  expect(panel("Current work")).toHaveAttribute("open");
  expect(panel("History 2 entries")).not.toHaveAttribute("open");
  const toggle = screen.getByRole("button", { name: "History 2 entries" });
  expect(
    document.getElementById(toggle.getAttribute("aria-controls")!),
  ).toHaveTextContent("Old content");
  await userEvent.click(toggle);
  await waitFor(() => expect(toggle).toHaveAttribute("aria-expanded", "true"));
  expect(panel("Current work")).toHaveAttribute("open");
  expect(toggle.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
});
test("collapsing retains the exact input nodes and unsaved values without persisting a visit preference", async () => {
  const view = render(
    <CollapsiblePanel title="Optional details" defaultOpen>
      <input aria-label="Notes" />
    </CollapsiblePanel>,
  );
  const user = userEvent.setup();
  const input = screen.getByLabelText("Notes");
  await user.type(input, "Unsubmitted notes");
  await user.click(screen.getByRole("button", { name: "Optional details" }));
  expect(panel("Optional details")).not.toHaveAttribute("open");
  await user.click(screen.getByRole("button", { name: "Optional details" }));
  expect(screen.getByLabelText("Notes")).toBe(input);
  expect(input).toHaveValue("Unsubmitted notes");
  view.unmount();
  render(
    <CollapsiblePanel title="Optional details">
      <input aria-label="Notes" />
    </CollapsiblePanel>,
  );
  expect(panel("Optional details")).not.toHaveAttribute("open");
});
test("native validation reveals every collapsed ancestor without remounting the input", async () => {
  render(
    <form>
      <CollapsiblePanel title="Outer">
        <CollapsiblePanel title="Inner">
          <input required aria-label="Required note" />
        </CollapsiblePanel>
      </CollapsiblePanel>
    </form>,
  );
  fireEvent.invalid(screen.getByLabelText("Required note"));
  expect(panel("Outer")).toHaveAttribute("open");
  expect(panel("Inner")).toHaveAttribute("open");
});
test("server errors and aria-invalid fields automatically reveal their panels", async () => {
  function Form() {
    const [error, setError] = useState(false);
    return (
      <>
        <button onClick={() => setError(true)}>Validate</button>
        <CollapsiblePanel title="Advanced">
          <input aria-label="Amount" aria-invalid={error} />
          {error && <p role="alert">Amount is invalid</p>}
        </CollapsiblePanel>
      </>
    );
  }
  render(<Form />);
  expect(panel("Advanced")).not.toHaveAttribute("open");
  await userEvent.click(screen.getByRole("button", { name: "Validate" }));
  await waitFor(() => expect(panel("Advanced")).toHaveAttribute("open"));
  expect(screen.getByRole("alert")).toBeVisible();
});
