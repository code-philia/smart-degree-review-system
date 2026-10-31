/* A damped height field: the surface propagates waves instead of stretching trails. */
import { WaterWaveSolver, POOL_GLSL, POOL_PATH, isInPool, poolRight } from './waterSurface';

/** Start the selected local pond effect; return a complete teardown for React navigation. */
export function startPondRenderer(canvas, waterHit, waterStage) {
  if (typeof WebGLRenderingContext === 'undefined') return () => {};
  let disposed = false;
  const shaders = [],
    textures = [];
  let buffer, image;

  waterHit.setAttribute('d', POOL_PATH);

  const field = new WaterWaveSolver(window.innerWidth <= 800 ? 256 : 384, window.innerWidth <= 800 ? 112 : 160, 4.8),
    pixels = new Uint8Array(field.cols * field.rows * 4);
  let gl,
    program,
    locations,
    heightTexture,
    loaded = false,
    frameId = 0,
    lastFrame = 0,
    lastStep = 0,
    lastWind = 0,
    lastStats = 0,
    previous = null;
  const vertex = `attribute vec2 position;varying vec2 uv;void main(){gl_Position=vec4(position,0.,1.);uv=vec2((position.x+1.)*.5,1.-(position.y+1.)*.5);}`;
  const fragment = `precision highp float;
    varying vec2 uv;uniform sampler2D photo;uniform sampler2D heightMap;
    uniform vec2 resolution;uniform vec2 imageSize;uniform vec2 texel;uniform float time;
    float heightAt(vec2 q){vec2 encodedHeight=texture2D(heightMap,clamp(q,texel,1.-texel)).rg;return (encodedHeight.r*65280.+encodedHeight.g*255.)/65535.*2.-1.;}
    ${POOL_GLSL}
    void main(){
      float scale=max(resolution.x/imageSize.x,resolution.y/imageSize.y);vec2 drawn=imageSize*scale;
      vec2 source=(uv*resolution-vec2(0.,(resolution.y-drawn.y)*.5))/drawn;vec2 p=source*imageSize;
      float depth=clamp((p.y-737.)/204.,0.,1.);float width=poolRight(p.y);
      float edge=smoothstep(750.,762.,p.y)*smoothstep(0.,14.,p.x-poolLeft(p.y))*(1.-smoothstep(width-30.,width,p.x));
      if(edge<.001||p.x<0.){gl_FragColor=vec4(0.);return;}
      vec2 q=vec2(p.x/width,pow(depth,.55));
      float hx=(heightAt(q+vec2(texel.x,0.))-heightAt(q-vec2(texel.x,0.)))/(2.*4.8*texel.x);
      float hy=(heightAt(q+vec2(0.,texel.y))-heightAt(q-vec2(0.,texel.y)))/(2.*texel.y);
      // Perspective-compressed wave fronts run across the pond, rather than rounded blobs.
      vec2 surface=vec2(q.x*4.8,q.y);
      float p1=surface.y*112.+surface.x*3.8+sin(surface.x*4.3-time*.17)*.75-time*3.4;
      float p2=surface.y*173.-surface.x*6.3+sin(surface.x*7.1+time*.13)*.55-time*4.6;
      float p3=surface.y*257.+surface.x*10.7-time*5.8;
      float p4=surface.y*367.-surface.x*16.1-time*5.7;
      float sy=.26*sin(p1)+.16*sin(p2)+.085*sin(p3)+.04*sin(p4);
      float sx=.012*sin(p1)-.018*sin(p2)+.013*sin(p3);
      hx=clamp(hx,-1.1,1.1)+sx;hy=clamp(hy,-1.3,1.3)+sy;
      float perspective=mix(.16,1.,depth);
      // A short vertical refraction breaks reflections into moving horizontal facets.
      vec2 refractOffset=clamp(vec2(hx*5.5,hy*6.5),vec2(-5.5,-3.5),vec2(5.5,3.5))*perspective;
      vec3 normal=normalize(vec3(-hx*.5,-hy*.92,1.));
      vec3 light=normalize(vec3(.18,-.38,1.));
      vec3 halfVector=normalize(light+vec3(0.,0.,1.));
      float glint=pow(max(dot(normal,halfVector),0.),165.);
      float broken=.55+.45*sin(surface.x*8.5+sin(surface.y*41.)+time*.15);
      float crest=pow(max(0.,.63*cos(p1)+.28*cos(p2)+.12*cos(p3)-.12),5.);
      float shade=clamp(hy,-.7,.7)*.055;
      vec3 color=texture2D(photo,source+refractOffset/imageSize).rgb;
      color=clamp(color+perspective*(vec3(1.,.96,.84)*(glint*.14+crest*broken*.16)-shade),0.,1.);
      gl_FragColor=vec4(color*edge,edge);
    }`;
  function compile(type, source) {
    const shader = gl.createShader(type);
    shaders.push(shader);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(shader));
    return shader;
  }
  function resize() {
    const r = canvas.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const ratio = Math.min(devicePixelRatio || 1, 1.25),
      w = Math.round(r.width * ratio),
      h = Math.round(r.height * ratio);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    gl.viewport(0, 0, w, h);
    gl.uniform2f(locations.resolution, r.width, r.height);
    return true;
  }
  let steps = 0;
  function frame(now) {
    frameId = 0;
    if (disposed || !loaded || document.hidden) {
      lastStep = 0;
      return;
    }
    if (now - lastFrame >= 31) {
      lastFrame = now;
      if (!lastStep) lastStep = now - 1000 / 60;
      let count = 0;
      while (now - lastStep >= 1000 / 60 && count < 4) {
        field.step();
        lastStep += 1000 / 60;
        count++;
        steps++;
      }
      if (count === 4) lastStep = now;
      if (now - lastWind > 900) {
        lastWind = now;
        const phase = now / 1000;
        field.disturb(
          0.1 + (Math.sin(phase * 0.37) + 1) * 0.34,
          0.17 + (Math.sin(phase * 0.21) + 1) * 0.26,
          0.0012,
          0.03,
        );
      }
      if (resize()) {
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, heightTexture);
        gl.texSubImage2D(
          gl.TEXTURE_2D,
          0,
          0,
          0,
          field.cols,
          field.rows,
          gl.RGBA,
          gl.UNSIGNED_BYTE,
          field.encode(pixels),
        );
        gl.uniform1f(locations.time, now / 1000);
        gl.drawArrays(gl.TRIANGLES, 0, 6);
      }
      if (now - lastStats > 500) {
        lastStats = now;
        canvas.dataset.energy = field.energy().toFixed(6);
        canvas.dataset.steps = String(steps);
      }
    }
    frameId = requestAnimationFrame(frame);
  }
  function start() {
    if (!disposed && loaded && !frameId && !document.hidden) {
      lastStep = 0;
      frameId = requestAnimationFrame(frame);
    }
  }
  function disturb(event) {
    if (disposed || document.hidden) return;
    const matrix = waterStage.getScreenCTM();
    if (!matrix) return;
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    if (!isInPool(p.x, p.y)) return;
    const depth = (p.y - 737) / 204,
      width = poolRight(p.y);
    if (p.x < 0 || p.x > width) return;
    const now = performance.now(),
      point = { x: p.x / width, y: Math.pow(depth, 0.55), time: now };
    if (previous && now - previous.time < 250) {
      const delta = Math.hypot((point.x - previous.x) * 4.8, point.y - previous.y);
      if (delta > 0.004) {
        const speed = delta / Math.max(0.012, (now - previous.time) / 1000);
        field.stroke(previous, point, Math.min(0.026, 0.009 + speed * 0.012));
        canvas.dataset.cursorStrokes = String(Number(canvas.dataset.cursorStrokes || 0) + 1);
        start();
      }
    }
    previous = point;
  }
  const pointerDown = (event) => {
    previous = null;
    disturb(event);
  };
  const pointerLeave = () => {
    previous = null;
  };
  waterHit.addEventListener('pointermove', disturb, { passive: true });
  waterHit.addEventListener('pointerdown', pointerDown, { passive: true });
  waterHit.addEventListener('pointerleave', pointerLeave);
  try {
    gl = canvas.getContext('webgl', {
      alpha: true,
      antialias: false,
      premultipliedAlpha: true,
      powerPreference: 'low-power',
    });
    if (!gl) throw Error('WebGL unavailable');
    program = gl.createProgram();
    gl.attachShader(program, compile(gl.VERTEX_SHADER, vertex));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fragment));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);
    buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, 'position');
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    locations = {
      resolution: gl.getUniformLocation(program, 'resolution'),
      imageSize: gl.getUniformLocation(program, 'imageSize'),
      texel: gl.getUniformLocation(program, 'texel'),
      time: gl.getUniformLocation(program, 'time'),
    };
    gl.uniform2f(locations.texel, 1 / field.cols, 1 / field.rows);
    gl.uniform1i(gl.getUniformLocation(program, 'photo'), 0);
    gl.uniform1i(gl.getUniformLocation(program, 'heightMap'), 1);
    function configureTexture() {
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    }
    const photo = gl.createTexture();
    textures.push(photo);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, photo);
    configureTexture();
    heightTexture = gl.createTexture();
    textures.push(heightTexture);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, heightTexture);
    configureTexture();
    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      gl.RGBA,
      field.cols,
      field.rows,
      0,
      gl.RGBA,
      gl.UNSIGNED_BYTE,
      field.encode(pixels),
    );
    image = new Image();
    image.onload = () => {
      if (disposed) return;
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, photo);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
      gl.uniform2f(locations.imageSize, image.naturalWidth, image.naturalHeight);
      loaded = true;
      canvas.dataset.renderer = 'height-field-webgl';
      canvas.dataset.mask = 'pool-only';
      start();
    };
    image.src = '/sjtu-siyuan-illustration.webp';
  } catch (error) {
    canvas.dataset.renderer = 'static';
    canvas.dataset.error = String(error.message);
    canvas.hidden = true;
  }
  const visibility = () => {
    if (document.hidden) {
      cancelAnimationFrame(frameId);
      frameId = 0;
      lastStep = 0;
      previous = null;
    } else start();
  };
  const contextLost = (event) => {
    event.preventDefault();
    loaded = false;
    cancelAnimationFrame(frameId);
    frameId = 0;
    canvas.hidden = true;
  };
  window.addEventListener('resize', start);
  document.addEventListener('visibilitychange', visibility);
  canvas.addEventListener('webglcontextlost', contextLost);
  start();
  return () => {
    disposed = true;
    cancelAnimationFrame(frameId);
    window.removeEventListener('resize', start);
    document.removeEventListener('visibilitychange', visibility);
    canvas.removeEventListener('webglcontextlost', contextLost);
    waterHit.removeEventListener('pointermove', disturb);
    waterHit.removeEventListener('pointerdown', pointerDown);
    waterHit.removeEventListener('pointerleave', pointerLeave);
    if (image) image.onload = null;
    if (gl) {
      for (const texture of textures) gl.deleteTexture(texture);
      for (const shader of shaders) gl.deleteShader(shader);
      if (buffer) gl.deleteBuffer(buffer);
      if (program) gl.deleteProgram(program);
    }
  };
}
