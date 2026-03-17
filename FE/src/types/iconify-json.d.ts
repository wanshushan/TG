declare module "@iconify-json/*/icons.json" {
    const icons: {
        icons: Record<
            string,
            {
                body: string;
                width?: number;
                height?: number;
                left?: number;
                top?: number;
            }
        >;
        width?: number;
        height?: number;
    };

    export default icons;
}
