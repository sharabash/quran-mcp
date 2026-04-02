import { mount } from "svelte";
import "./documentation-global.css";
import App from "./App.svelte";

mount(App, { target: document.getElementById("app")! });
