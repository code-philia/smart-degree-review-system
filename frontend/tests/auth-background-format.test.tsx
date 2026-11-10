import { fireEvent, render } from '@testing-library/react';
import { expect, it } from 'vitest';
import AuthCampusScene from '../src/pages/authCampus/AuthCampusScene';

const avif='/login-campus-B-v5-750f63ec.avif';
const webp='/login-campus-B-v5-229caf6d.webp';
const png='/login-campus-B-v5-b25c6008.png';

it('preloads the preferred AVIF and uses the browser-selected exact image for the scene', () => {
  const {container}=render(<AuthCampusScene />);
  const picture=container.querySelector('picture');
  expect(picture).toBeInTheDocument();
  expect(picture!.querySelector('source[type="image/avif"]')).toHaveAttribute('srcset',avif);
  const preload=document.querySelector('link[rel="preload"][as="image"]');
  expect(preload).toHaveAttribute('href',avif);
  expect(preload).toHaveAttribute('type','image/avif');
  const image=picture!.querySelector('img')!;
  expect(image).toHaveAttribute('src',webp);
  expect(container.querySelector('.scene')).not.toHaveStyle({backgroundImage:`url("${png}")`});
  Object.defineProperty(image,'currentSrc',{configurable:true,value:location.origin+avif});
  fireEvent.load(image);
  expect(container.querySelector('.scene')).toHaveStyle({backgroundImage:`url("${location.origin+avif}")`});
});

it('uses WebP when selected by the browser without ever starting the original PNG', () => {
  const {container}=render(<AuthCampusScene />);
  const picture=container.querySelector('picture');
  expect(picture).toBeInTheDocument();
  const image=picture!.querySelector('img')!;
  Object.defineProperty(image,'currentSrc',{configurable:true,value:location.origin+webp});
  fireEvent.load(image);
  expect(container.querySelector('.scene')).toHaveStyle({backgroundImage:`url("${location.origin+webp}")`});
  expect(document.querySelector(`link[href="${png}"]`)).not.toBeInTheDocument();
});

it('recovers from AVIF failure via WebP, then retains the original PNG as a final failure fallback', () => {
  const {container}=render(<AuthCampusScene />);
  const picture=container.querySelector('picture');
  expect(picture).toBeInTheDocument();
  const image=picture!.querySelector('img')!;
  fireEvent.error(image);
  expect(picture!.querySelector('source[type="image/avif"]')).not.toBeInTheDocument();
  expect(image).toHaveAttribute('src',webp);
  fireEvent.error(image);
  expect(image).toHaveAttribute('src',png);
  fireEvent.load(image);
  expect(container.querySelector('.scene')).toHaveStyle({backgroundImage:`url("${image.src}")`});
  fireEvent.error(image);
  expect(image).toHaveAttribute('src',png);
});
