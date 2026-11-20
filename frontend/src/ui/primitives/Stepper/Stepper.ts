/**
 * Fallback chỉ để tsc resolve được './Stepper' (TS không hiểu .weapp/.h5).
 * Webpack (MultiPlatformPlugin) luôn ưu tiên Stepper.weapp.tsx /
 * Stepper.h5.tsx khi tồn tại nên file này KHÔNG BAO GIỜ được bundle.
 */
export { default } from './Stepper.h5'
export type { StepperProps } from './Stepper.types'
