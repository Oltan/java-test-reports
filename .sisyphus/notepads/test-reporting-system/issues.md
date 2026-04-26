# Issues & Gotchas

## ffmpeg Not Available
- `ffmpeg` not installed in WSL environment
- Cannot `sudo apt install` due to missing password prompt
- **Workaround**: Task 2 (video) will use ProcessBuilder that fails gracefully; 
  video validation tests will be skipped until ffmpeg is installed
