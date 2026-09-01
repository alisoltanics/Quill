module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['<rootDir>/tests/**/*.test.ts'],
  moduleFileExtensions: ['ts', 'tsx', 'js'],
  collectCoverageFrom: ['lib/**/*.ts'],
}
