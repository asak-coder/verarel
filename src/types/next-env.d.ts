/// <reference types="react" />
/// <reference types="react-dom" />
/// <reference types="node" />

declare module "react";
declare module "react-dom";
declare module "swr";

declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: unknown;
  }
}
