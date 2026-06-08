import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

function makeElement() {
  return {
    style: {},
    classList: { add() {}, remove() {}, toggle() {} },
    dataset: {},
    value: "",
    textContent: "",
    hidden: false,
    disabled: false,
    append() {},
    appendChild() {},
    replaceChildren() {},
    addEventListener() {},
    setAttribute() {},
    focus() {},
  };
}

const elements = new Map();
const context = {
  console,
  window: { addEventListener() {}, location: { href: "" } },
  navigator: {},
  localStorage: {
    getItem() { return null; },
    setItem() {},
  },
  document: {
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, makeElement());
      }
      return elements.get(id);
    },
    createElement() {
      return makeElement();
    },
  },
  fetch() {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ session_id: "test-session", messages: [] }),
    });
  },
  Blob,
  FileReader: class {},
  Image: class {},
  TextDecoder,
};

vm.createContext(context);
vm.runInContext(fs.readFileSync("static/app.js", "utf8"), context);

assert.equal(context.inferImageMime({ name: "photo.JPG", type: "" }), "image/jpeg");
assert.equal(context.inferImageMime({ name: "scan.tiff", type: "" }), "image/tiff");
assert.equal(context.inferImageMime({ name: "phone.heic", type: "" }), "image/heic");
assert.equal(context.isLikelyImageFile({ name: "phone.heic", type: "" }), true);
assert.equal(context.isLikelyImageFile({ name: "notes.txt", type: "" }), false);

console.log("frontend upload helper tests OK");
