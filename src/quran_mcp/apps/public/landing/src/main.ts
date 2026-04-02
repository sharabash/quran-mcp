import { mount } from "svelte";
import "./landing-global.css";
import App from "./App.svelte";

mount(App, { target: document.getElementById("app")! });
